"""Agent routes: CRUD, and per-user access grants.

An agent carries its own instruction, KB scope, and model/retrieval settings.
The owner may edit/delete/grant; granted users may only use it in chat. The KB
set is validated against the owner's access on every write.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import exists, select

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.config import settings
from backend.app.models import Agent, AgentAccess, ChatSession, User
from backend.app.schemas import (
    AgentAccessGrant,
    AgentAccessOut,
    AgentCreate,
    AgentOut,
    AgentUpdate,
)
from backend.app.services.access import (
    accessible_agents,
    can_manage_agent,
    can_use_agent,
    validate_agent_kb_ids,
)

router = APIRouter(prefix="/agents", tags=["agents"])


def _load_agent(db: DbSession, agent_id: uuid.UUID) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def _require_manage(db: DbSession, user: User, agent: Agent) -> None:
    if not can_manage_agent(db, user, agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not the agent owner"
        )


@router.get("", response_model=list[AgentOut])
def list_agents(current_user: CurrentUser, db: DbSession) -> list[Agent]:
    return accessible_agents(db, current_user)


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, current_user: CurrentUser, db: DbSession) -> Agent:
    try:
        kb_ids = validate_agent_kb_ids(db, current_user, payload.kb_ids)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    agent = Agent(
        owner_user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        kb_ids=kb_ids,
        model_name=payload.model_name or settings.llm_model,
        temperature=payload.temperature
        if payload.temperature is not None
        else settings.default_temperature,
        retrieval_top_k=payload.retrieval_top_k or settings.default_retrieval_top_k,
        retrieval_threshold=payload.retrieval_threshold
        if payload.retrieval_threshold is not None
        else settings.default_retrieval_threshold,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> Agent:
    agent = _load_agent(db, agent_id)
    # Any user who can use the agent may view its config.
    if not can_use_agent(db, current_user, agent):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: uuid.UUID, payload: AgentUpdate, current_user: CurrentUser, db: DbSession
) -> Agent:
    agent = _load_agent(db, agent_id)
    _require_manage(db, current_user, agent)

    data = payload.model_dump(exclude_unset=True)
    if "kb_ids" in data:
        try:
            # Re-validate the entire KB set against the owner's current access.
            data["kb_ids"] = validate_agent_kb_ids(db, current_user, data["kb_ids"])
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    for field, value in data.items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    agent = _load_agent(db, agent_id)
    _require_manage(db, current_user, agent)
    in_use = db.scalar(select(exists().where(ChatSession.agent_id == agent_id)))
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent is in use by one or more chat sessions",
        )
    db.delete(agent)  # cascades to access grants
    db.commit()


# --- Access grants ---
@router.get("/{agent_id}/access", response_model=list[AgentAccessOut])
def list_access(
    agent_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> list[AgentAccessOut]:
    agent = _load_agent(db, agent_id)
    _require_manage(db, current_user, agent)
    rows = db.scalars(
        select(AgentAccess).where(AgentAccess.agent_id == agent_id)
    ).all()
    return [
        AgentAccessOut(
            user_id=r.user.id, email=r.user.email, display_name=r.user.display_name
        )
        for r in rows
    ]


@router.post(
    "/{agent_id}/access", response_model=AgentAccessOut, status_code=status.HTTP_201_CREATED
)
def add_access(
    agent_id: uuid.UUID,
    payload: AgentAccessGrant,
    current_user: CurrentUser,
    db: DbSession,
) -> AgentAccessOut:
    agent = _load_agent(db, agent_id)
    _require_manage(db, current_user, agent)
    target = db.scalar(select(User).where(User.email == payload.email))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id != agent.owner_user_id:
        existing = db.scalar(
            select(AgentAccess).where(
                AgentAccess.agent_id == agent_id, AgentAccess.user_id == target.id
            )
        )
        if existing is None:
            db.add(AgentAccess(agent_id=agent_id, user_id=target.id))
            db.commit()
    return AgentAccessOut(
        user_id=target.id, email=target.email, display_name=target.display_name
    )


@router.delete(
    "/{agent_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_access(
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    agent = _load_agent(db, agent_id)
    _require_manage(db, current_user, agent)
    grant = db.scalar(
        select(AgentAccess).where(
            AgentAccess.agent_id == agent_id, AgentAccess.user_id == user_id
        )
    )
    if grant is not None:
        db.delete(grant)
        db.commit()
