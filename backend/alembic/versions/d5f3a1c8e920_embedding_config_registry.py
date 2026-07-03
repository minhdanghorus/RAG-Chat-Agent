"""embedding config registry + nullable chunk embeddings

Revision ID: d5f3a1c8e920
Revises: c4a1f0e2d3b7
Create Date: 2026-07-03 15:30:00.000000

Adds the `embedding_config` registry (the DB's record of which embedding model
produced its vectors) and makes `chunks.embedding` nullable so a NULL can mark a
chunk awaiting re-embedding during a model switch.

Seeding rule:
- Fresh / empty database (no chunks): align the embedding column dimension to the
  configured `EMBEDDING_DIM` and seed the registry from settings, so a new clone
  boots cleanly at whatever model is configured.
- Existing database with data: preserve the stored vectors and register what they
  actually are — the live column dimension, plus the configured model name when
  its dimension matches, otherwise the legacy default that produced them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from backend.app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "d5f3a1c8e920"
down_revision: Union[str, Sequence[str], None] = "c4a1f0e2d3b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HNSW_INDEX = "ix_chunks_embedding_hnsw"
# The only embedding model in use before this registry existed (initial schema
# hardcoded halfvec(3072) for gemini/gemini-embedding-001). Used to label
# pre-existing vectors whose dimension no longer matches the configured model.
_LEGACY_MODEL = "gemini/gemini-embedding-001"


def _column_dim(conn) -> int:
    # For pgvector's vector/halfvec types, atttypmod holds the declared dimension.
    return conn.execute(
        sa.text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
    ).scalar_one()


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "embedding_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("pending_model", sa.String(length=255), nullable=True),
        sa.Column("pending_dim", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_embedding_config_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Make embeddings nullable so re-embedding can clear them in place.
    op.alter_column("chunks", "embedding", nullable=True)

    has_data = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM chunks)")).scalar_one()
    current_dim = _column_dim(conn)
    target_dim = settings.embedding_dim

    if not has_data:
        # Fresh install: adopt the configured dimension and model outright.
        if current_dim != target_dim:
            op.execute(f'DROP INDEX IF EXISTS "{_HNSW_INDEX}"')
            op.execute(
                f"ALTER TABLE chunks ALTER COLUMN embedding "
                f"TYPE halfvec({target_dim}) USING NULL"
            )
            op.execute(
                f'CREATE INDEX "{_HNSW_INDEX}" ON chunks '
                f"USING hnsw (embedding halfvec_cosine_ops)"
            )
        seed_model = settings.embedding_model
        seed_dim = target_dim
    else:
        # Existing data: keep the vectors; register what they actually are.
        seed_dim = current_dim
        seed_model = (
            settings.embedding_model if settings.embedding_dim == current_dim else _LEGACY_MODEL
        )

    conn.execute(
        sa.text(
            "INSERT INTO embedding_config (id, model, dim) VALUES (1, :model, :dim)"
        ),
        {"model": seed_model, "dim": seed_dim},
    )


def downgrade() -> None:
    op.drop_table("embedding_config")
    # Restore NOT NULL. This fails if any embedding is NULL (i.e. a re-embed was
    # left unfinished); complete or roll back the re-embed first.
    op.alter_column("chunks", "embedding", nullable=False)
