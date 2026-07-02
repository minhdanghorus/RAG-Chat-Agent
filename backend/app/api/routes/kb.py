"""Knowledge-base routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.api.deps import CurrentUser, DbSession, get_user_team_ids
from backend.app.models import KnowledgeBase
from backend.app.schemas import KBCreate, KBOut
from backend.app.services.access import accessible_kbs, can_manage_kb, can_read_kb

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("", response_model=list[KBOut])
def list_kbs(current_user: CurrentUser, db: DbSession) -> list[KnowledgeBase]:
    return accessible_kbs(db, current_user)


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
def create_kb(payload: KBCreate, current_user: CurrentUser, db: DbSession) -> KnowledgeBase:
    if payload.team_id is not None:
        # Team KB: caller must belong to the team.
        if payload.team_id not in get_user_team_ids(db, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of that team",
            )
        kb = KnowledgeBase(name=payload.name, owner_team_id=payload.team_id)
    else:
        # Personal KB.
        kb = KnowledgeBase(name=payload.name, owner_user_id=current_user.id)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def _get_kb_or_404(db: DbSession, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KB not found")
    return kb


@router.get("/{kb_id}", response_model=KBOut)
def get_kb(kb_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> KnowledgeBase:
    kb = _get_kb_or_404(db, kb_id)
    if not can_read_kb(db, current_user, kb):
        # 404 (not 403) so existence of another tenant's KB isn't revealed.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KB not found")
    return kb


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(kb_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    kb = _get_kb_or_404(db, kb_id)
    if not can_read_kb(db, current_user, kb):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KB not found")
    if not can_manage_kb(db, current_user, kb):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this KB"
        )
    db.delete(kb)  # cascades to documents + chunks
    db.commit()
