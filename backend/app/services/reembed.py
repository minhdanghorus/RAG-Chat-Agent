"""Re-embedding orchestration: migrate stored vectors to the configured model.

Switching embedding models is not a pure config change — stored vectors are
model- and dimension-specific. This command coordinates the switch against the
live database, re-embedding each chunk from its stored `content` (no re-upload
needed for a pure model swap).

Design and resumability
-----------------------
The registry (`embedding_config`) commits `model`/`dim` only at the very end. A
switch in progress is marked by `pending_model`/`pending_dim`; the committed
`model`/`dim` still describe the vectors, so mismatch validation keeps failing
until completion. A chunk with a NULL embedding is the unit of remaining work.

Phases (each idempotent, so an interrupted run can simply be re-invoked):
  1. Start (once):  record the pending target and clear old vectors atomically
                    (ALTER ... USING NULL for a dimension change, else UPDATE to
                    NULL), after dropping the HNSW index.
  2. Backfill:      per document, embed its NULL chunks in batches, committing
                    per batch; mark the document ready when it has no NULL chunks.
  3. Finalize:      rebuild the HNSW index, then commit the registry to the new
                    model/dim and clear the pending marker.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models import Chunk, Document, DocumentStatus, EmbeddingConfig
from backend.app.services.embeddings import embed_texts

_HNSW_INDEX = "ix_chunks_embedding_hnsw"


def _column_dim(db: Session) -> int:
    # atttypmod holds the declared dimension for pgvector's halfvec type.
    return db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
    ).scalar_one()


def _null_chunk_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None)))


def _drop_index(db: Session) -> None:
    db.execute(text(f'DROP INDEX IF EXISTS "{_HNSW_INDEX}"'))
    db.commit()


def _create_index(db: Session) -> None:
    db.execute(
        text(
            f'CREATE INDEX IF NOT EXISTS "{_HNSW_INDEX}" ON chunks '
            f"USING hnsw (embedding halfvec_cosine_ops)"
        )
    )
    db.commit()


def _alter_dim(db: Session, target_dim: int) -> None:
    db.execute(
        text(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec({target_dim}) USING NULL")
    )


def reembed(batch_size: int = 64) -> int:
    """Run the re-embed orchestration. Returns a process exit code (0 = success)."""
    target_model = settings.embedding_model
    target_dim = settings.embedding_dim

    with SessionLocal() as db:
        cfg = db.scalar(select(EmbeddingConfig).limit(1))
        if cfg is None:
            print(
                "No embedding_config registry row found. Run migrations first: "
                "uv run alembic upgrade head"
            )
            return 1

        switch_pending = cfg.pending_model is not None
        pending_matches = (
            switch_pending
            and cfg.pending_model == target_model
            and cfg.pending_dim == target_dim
        )
        already_active = cfg.model == target_model and cfg.dim == target_dim

        if already_active and not switch_pending and _null_chunk_count(db) == 0:
            print(f"Embeddings already match '{target_model}' ({target_dim}-dim); nothing to do.")
            return 0

        # --- Phase 1: start (idempotent) ---
        # Fresh start when no switch is pending, or when settings changed to a
        # different target mid-switch (re-null and re-target).
        fresh_start = not switch_pending or not pending_matches
        _drop_index(db)

        if fresh_start:
            cfg.pending_model = target_model
            cfg.pending_dim = target_dim
            if _column_dim(db) != target_dim:
                _alter_dim(db, target_dim)  # clears all vectors as it changes type
            else:
                db.execute(update(Chunk).values(embedding=None))
            db.commit()
        elif _column_dim(db) != target_dim:
            # Resuming a dimension change that was interrupted before ALTER.
            _alter_dim(db, target_dim)
            db.commit()

        # --- Phase 2: backfill ---
        try:
            total = _backfill(db, batch_size)
        except Exception as exc:  # noqa: BLE001 - report progress and stay resumable
            db.rollback()
            remaining_chunks = _null_chunk_count(db)
            remaining_docs = db.scalar(
                select(func.count(func.distinct(Chunk.document_id))).where(
                    Chunk.embedding.is_(None)
                )
            )
            print(
                f"Re-embed failed: {exc}\n"
                f"{remaining_chunks} chunk(s) across {remaining_docs} document(s) still "
                f"pending. Re-run the command to resume."
            )
            return 1

        # --- Phase 3: finalize ---
        _create_index(db)
        cfg.model = target_model
        cfg.dim = target_dim
        cfg.pending_model = None
        cfg.pending_dim = None
        db.commit()

    print(f"Re-embed complete: {total} chunk(s) embedded with '{target_model}' ({target_dim}-dim).")
    return 0


def _backfill(db: Session, batch_size: int) -> int:
    """Embed all NULL chunks, grouped by document. Returns chunks embedded."""
    doc_ids = list(
        db.scalars(
            select(Chunk.document_id).where(Chunk.embedding.is_(None)).distinct()
        ).all()
    )
    # Mark documents with pending work as processing so the UI shows the switch.
    if doc_ids:
        db.execute(
            update(Document)
            .where(Document.id.in_(doc_ids))
            .values(status=DocumentStatus.processing)
        )
        db.commit()

    embedded = 0
    for doc_id in doc_ids:
        embedded += _backfill_document(db, doc_id, batch_size)
        db.execute(
            update(Document).where(Document.id == doc_id).values(status=DocumentStatus.ready)
        )
        db.commit()
    return embedded


def _backfill_document(db: Session, doc_id: uuid.UUID, batch_size: int) -> int:
    rows = db.execute(
        select(Chunk.id, Chunk.content)
        .where(Chunk.document_id == doc_id, Chunk.embedding.is_(None))
        .order_by(Chunk.chunk_index)
    ).all()

    embedded = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = embed_texts([content for _, content in batch])
        for (chunk_id, _), vector in zip(batch, vectors, strict=True):
            db.execute(update(Chunk).where(Chunk.id == chunk_id).values(embedding=vector))
        db.commit()  # commit per batch so an interruption loses at most one batch
        embedded += len(batch)
    return embedded
