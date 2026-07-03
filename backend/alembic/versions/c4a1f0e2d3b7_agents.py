"""agents, agent access, and chat_sessions.agent_id (+ Default Assistant backfill)

Revision ID: c4a1f0e2d3b7
Revises: 3e22bac4a006
Create Date: 2026-07-03 04:30:00.000000

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4a1f0e2d3b7"
down_revision: Union[str, Sequence[str], None] = "3e22bac4a006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Baseline instruction for seeded Default Assistant agents (mirrors the MVP's
# hardcoded SYSTEM_PROMPT at the time of this migration).
_DEFAULT_PROMPT = (
    "You are a helpful assistant that answers questions strictly about the user's "
    "documents. Always call the retrieve_kb tool to search the user's knowledge "
    "bases before answering a question about their content. Base your answer only "
    "on the retrieved passages and refer to their sources (e.g. [1], [2]). If the "
    "retrieved passages do not contain the answer, say you don't have enough "
    "grounding in the documents to answer, rather than guessing."
    "Your name is Miku and you are a virtual assistant for the user. You are helpful, kind, and cute."
)
_DEFAULT_MODEL = "google/gemma-4-31b-it"
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_TOP_K = 5
_DEFAULT_THRESHOLD = 0.0


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("kb_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("retrieval_top_k", sa.Integer(), nullable=False),
        sa.Column("retrieval_threshold", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agents_owner_user_id"), "agents", ["owner_user_id"], unique=False)

    op.create_table(
        "agent_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "user_id", name="uq_agent_access_agent_user"),
    )
    op.create_index(op.f("ix_agent_access_agent_id"), "agent_access", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_access_user_id"), "agent_access", ["user_id"], unique=False)

    op.add_column("chat_sessions", sa.Column("agent_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_chat_sessions_agent_id"), "chat_sessions", ["agent_id"], unique=False
    )
    op.create_foreign_key(
        "fk_chat_sessions_agent_id",
        "chat_sessions",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _backfill_default_assistants()


def _backfill_default_assistants() -> None:
    """Per user owning sessions, create a Default Assistant (union of that user's
    session kb_ids) and point their sessions' agent_id at it."""
    conn = op.get_bind()
    owners = conn.execute(
        sa.text("SELECT DISTINCT user_id FROM chat_sessions WHERE agent_id IS NULL")
    ).fetchall()
    for (owner_id,) in owners:
        rows = conn.execute(
            sa.text("SELECT kb_ids FROM chat_sessions WHERE user_id = :uid"),
            {"uid": owner_id},
        ).fetchall()
        kb_union: set[str] = set()
        for (kb_ids,) in rows:
            for kid in kb_ids or []:
                kb_union.add(str(kid))

        agent_id = uuid.uuid4()
        conn.execute(
            sa.text(
                """
                INSERT INTO agents (
                    id, owner_user_id, name, description, system_prompt, kb_ids,
                    model_name, temperature, retrieval_top_k, retrieval_threshold
                )
                VALUES (
                    :id, :owner, 'Default Assistant',
                    'Migrated from your existing chats.', :prompt, CAST(:kb_ids AS uuid[]),
                    :model, :temp, :top_k, :threshold
                )
                """
            ),
            {
                "id": agent_id,
                "owner": owner_id,
                "prompt": _DEFAULT_PROMPT,
                "kb_ids": [str(k) for k in kb_union],
                "model": _DEFAULT_MODEL,
                "temp": _DEFAULT_TEMPERATURE,
                "top_k": _DEFAULT_TOP_K,
                "threshold": _DEFAULT_THRESHOLD,
            },
        )

        conn.execute(
            sa.text(
                "UPDATE chat_sessions SET agent_id = :aid "
                "WHERE user_id = :uid AND agent_id IS NULL"
            ),
            {"aid": agent_id, "uid": owner_id},
        )


def downgrade() -> None:
    op.drop_constraint("fk_chat_sessions_agent_id", "chat_sessions", type_="foreignkey")
    op.drop_index(op.f("ix_chat_sessions_agent_id"), table_name="chat_sessions")
    op.drop_column("chat_sessions", "agent_id")

    op.drop_index(op.f("ix_agent_access_user_id"), table_name="agent_access")
    op.drop_index(op.f("ix_agent_access_agent_id"), table_name="agent_access")
    op.drop_table("agent_access")

    op.drop_index(op.f("ix_agents_owner_user_id"), table_name="agents")
    op.drop_table("agents")
