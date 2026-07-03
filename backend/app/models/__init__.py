"""SQLAlchemy ORM models for the RAG Chat Agent.

Entities and the isolation model:
- User belongs to zero or more Teams via Membership.
- KnowledgeBase (KB) is owned by exactly one User (personal) OR one Team (shared).
- Document belongs to a KB; Chunk belongs to a Document and carries kb_id
  (denormalized) as the authoritative isolation key for retrieval.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Team(TimestampMixin, Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")
    team: Mapped[Team] = relationship(back_populates="memberships")


class KnowledgeBase(TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "(owner_user_id IS NOT NULL) <> (owner_team_id IS NOT NULL)",
            name="ck_kb_single_owner",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="kb", cascade="all, delete-orphan"
    )


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        String(20), default=DocumentStatus.pending, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    kb: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(TimestampMixin, Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # kb_id is denormalized here so retrieval can filter by it directly.
    kb_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: a NULL embedding marks a chunk awaiting (re-)embedding during a
    # model switch (see services/reembed.py). The column's dimension is fixed by
    # the DB schema and tracked in embedding_config, not bound here, so switching
    # models is a migration/reembed concern rather than an import-time constant.
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


class EmbeddingConfig(Base):
    """Single-row registry of the embedding model that produced the stored vectors.

    This is the database's own record of "what the vectors actually are", as
    opposed to application settings, which express "what is desired". A mismatch
    between the two is resolved by re-embedding (services/reembed.py). While a
    switch is in progress, `pending_model`/`pending_dim` hold the target and
    `model`/`dim` still describe the committed vectors, so mismatch validation
    keeps signalling until the switch completes.
    """

    __tablename__ = "embedding_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_embedding_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_model: Mapped[str | None] = mapped_column(String(255))
    pending_dim: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Agent(TimestampMixin, Base):
    """A configurable assistant: instruction, KB scope, and model/retrieval tuning.

    Owned by a single user. Sessions hold a live reference (see ChatSession.agent_id),
    so edits here apply to future messages in existing sessions. The KB set is
    validated against the owner's access on every write (services/access.py).
    """

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Retrieval scope: KBs the owner could read at write time (trusted as stored).
    kb_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), default=list, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_threshold: Mapped[float] = mapped_column(Float, nullable=False)

    access_grants: Mapped[list["AgentAccess"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentAccess(TimestampMixin, Base):
    """A per-user grant: the granted user may use the agent (owner grants/revokes)."""

    __tablename__ = "agent_access"
    __table_args__ = (
        UniqueConstraint("agent_id", "user_id", name="uq_agent_access_agent_user"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    agent: Mapped[Agent] = relationship(back_populates="access_grants")
    user: Mapped[User] = relationship()


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    # id doubles as the LangGraph checkpointer thread_id.
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512))
    # Live reference to the agent driving this session (resolved at message time).
    # RESTRICT: an agent cannot be deleted while a session still references it.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), index=True
    )
    # Legacy per-session KB selection. Kept for rollback; no longer read (agent
    # KBs now define retrieval scope). Dropped in a later cleanup change.
    kb_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), default=list, nullable=False)


__all__ = [
    "User",
    "Team",
    "Membership",
    "KnowledgeBase",
    "Document",
    "DocumentStatus",
    "Chunk",
    "ChatSession",
    "Agent",
    "AgentAccess",
]
