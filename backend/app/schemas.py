"""Pydantic request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


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


# --- Chat ---
class SessionCreate(BaseModel):
    kb_ids: list[uuid.UUID]
    title: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    kb_ids: list[uuid.UUID]
    created_at: datetime


class MessageRequest(BaseModel):
    content: str


class Citation(BaseModel):
    document_id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    chunk_index: int
    snippet: str
