"""Knowledge-base access control — the authorization gate.

Single source of truth for "which KBs may this user see/manage". Every route
and the retrieval tool resolve access through these helpers so isolation is
enforced consistently.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_user_team_ids
from backend.app.models import KnowledgeBase, User


def accessible_kbs(db: Session, user: User) -> list[KnowledgeBase]:
    """KBs the user may read: their personal KBs plus their teams' KBs."""
    team_ids = get_user_team_ids(db, user.id)
    conditions = [KnowledgeBase.owner_user_id == user.id]
    if team_ids:
        conditions.append(KnowledgeBase.owner_team_id.in_(team_ids))
    return list(db.scalars(select(KnowledgeBase).where(or_(*conditions))).all())


def accessible_kb_ids(db: Session, user: User) -> set[uuid.UUID]:
    return {kb.id for kb in accessible_kbs(db, user)}


def can_read_kb(db: Session, user: User, kb: KnowledgeBase) -> bool:
    if kb.owner_user_id == user.id:
        return True
    if kb.owner_team_id is not None:
        return kb.owner_team_id in get_user_team_ids(db, user.id)
    return False


def can_manage_kb(db: Session, user: User, kb: KnowledgeBase) -> bool:
    """Manage = upload documents / delete KB.

    Personal KB: only the owning user. Team KB: any member of the owning team.
    (For the MVP, read and manage coincide; kept separate for future roles.)
    """
    return can_read_kb(db, user, kb)


def resolve_selected_kb_ids(
    db: Session, user: User, requested: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    """Intersect requested KB ids with the user's accessible set.

    Raises PermissionError if any requested id is not accessible, so callers
    can surface a 403 rather than silently narrowing the selection.
    """
    allowed = accessible_kb_ids(db, user)
    requested_set = set(requested)
    forbidden = requested_set - allowed
    if forbidden:
        raise PermissionError(f"KBs not accessible: {sorted(str(x) for x in forbidden)}")
    return list(requested_set)
