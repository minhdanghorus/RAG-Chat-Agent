"""Embedding configuration registry.

The database records which embedding model produced its stored vectors (the
`embedding_config` row). Application settings express the desired model. These
helpers read the registry and compare it against settings so a mismatch is
detected and reported with an actionable remedy, rather than surfacing as a raw
pgvector dimension error on insert.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models import EmbeddingConfig

# How a user resolves a mismatch. Kept here so startup and ingestion report it
# identically.
REEMBED_COMMAND = "uv run python -m backend.app.cli reembed"


@dataclass(frozen=True)
class ConfigMismatch:
    """A detected disagreement between settings and the registry."""

    configured_model: str
    configured_dim: int
    active_model: str
    active_dim: int

    @property
    def message(self) -> str:
        return (
            f"Embedding configuration mismatch: settings request "
            f"'{self.configured_model}' ({self.configured_dim}-dim) but the database "
            f"was built with '{self.active_model}' ({self.active_dim}-dim). "
            f"Stored vectors are model- and dimension-specific and cannot be mixed. "
            f"Run `{REEMBED_COMMAND}` to re-embed stored chunks with the configured model."
        )


def get_active_config(db: Session) -> EmbeddingConfig | None:
    """Return the single registry row, or None if it has not been seeded."""
    return db.scalar(select(EmbeddingConfig).limit(1))


def check_settings_match(db: Session) -> ConfigMismatch | None:
    """Compare settings against the registry.

    Returns a ConfigMismatch if the configured model or dimension differs from
    the committed registry values, otherwise None. A missing registry row is
    treated as "not yet seeded" (None), not a mismatch — migrations seed it.
    Both model name and dimension are compared, so switching between different
    models of equal dimension is also detected.
    """
    active = get_active_config(db)
    if active is None:
        return None
    if active.model == settings.embedding_model and active.dim == settings.embedding_dim:
        return None
    return ConfigMismatch(
        configured_model=settings.embedding_model,
        configured_dim=settings.embedding_dim,
        active_model=active.model,
        active_dim=active.dim,
    )
