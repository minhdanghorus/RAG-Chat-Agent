"""Pydantic request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Auth ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None = None


# --- Knowledge bases ---
class KBCreate(BaseModel):
    name: str
    # Exactly one of these identifies the owner. Omit team_id for a personal KB.
    team_id: uuid.UUID | None = None


class KBOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None
    owner_team_id: uuid.UUID | None
    created_at: datetime


# --- Documents ---
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    content_type: str
    status: str
    error: str | None = None
    chunk_count: int
    created_at: datetime


# --- Agents ---
class AgentCreate(BaseModel):
    name: str
    system_prompt: str
    description: str | None = None
    kb_ids: list[uuid.UUID] = Field(default_factory=list)
    # Model / retrieval settings default from global config when omitted.
    model_name: str | None = None
    temperature: float | None = None
    retrieval_top_k: int | None = None
    retrieval_threshold: float | None = None


class AgentUpdate(BaseModel):
    """All fields optional; only provided fields are changed (KB set re-validated)."""

    name: str | None = None
    system_prompt: str | None = None
    description: str | None = None
    kb_ids: list[uuid.UUID] | None = None
    model_name: str | None = None
    temperature: float | None = None
    retrieval_top_k: int | None = None
    retrieval_threshold: float | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    description: str | None
    system_prompt: str
    kb_ids: list[uuid.UUID]
    model_name: str
    temperature: float
    retrieval_top_k: int
    retrieval_threshold: float
    created_at: datetime


class AgentAccessGrant(BaseModel):
    email: EmailStr


class AgentAccessOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    display_name: str | None = None


# --- Chat ---
class SessionCreate(BaseModel):
    agent_id: uuid.UUID
    title: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    agent_id: uuid.UUID | None
    agent_name: str | None = None
    created_at: datetime


class MessageRequest(BaseModel):
    content: str


class Citation(BaseModel):
    document_id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    chunk_index: int
    snippet: str
