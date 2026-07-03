"""Tests for the reembed orchestration.

reembed() operates globally on every chunk, so each test runs against its own
freshly-migrated temporary database (isolated from the shared dev DB). Embeddings
are faked for determinism — the gateway is never called.

Covered scenarios (tasks 4.5 / 4.6):
- full switch with a dimension change (column altered, index rebuilt);
- model-only switch at the same dimension;
- failure mid-backfill leaves a resumable state with the registry unchanged;
- resuming completes the switch without re-nulling already-embedded chunks.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.models import (
    Chunk,
    Document,
    DocumentStatus,
    EmbeddingConfig,
    KnowledgeBase,
    User,
)
from backend.app.services import reembed as reembed_mod

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE_DIM = settings.embedding_dim  # migration seeds the temp DB at this dim/model
_BASE_MODEL = settings.embedding_model


def _admin_conninfo(url) -> str:
    return (
        f"host={url.host} port={url.port} user={url.username} "
        f"password={url.password} dbname=postgres"
    )


def _fake_embed(texts: list[str]) -> list[list[float]]:
    # Deterministic vectors of the currently-configured dimension. The first
    # component encodes the text length so re-embeds are observably different.
    dim = settings.embedding_dim
    return [[float(len(t) % 7)] + [0.13] * (dim - 1) for t in texts]


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker]:
    base = make_url(settings.database_url)
    name = f"rag_reembed_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(_admin_conninfo(base), autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    temp_url = base.set(database=name)
    try:
        env = {**os.environ, "DATABASE_URL": temp_url.render_as_string(hide_password=False)}
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=_REPO_ROOT, env=env, check=True, capture_output=True, text=True,
        )
        engine = create_engine(temp_url, future=True)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        # Point the orchestration at the temp DB and stub out the gateway.
        monkeypatch.setattr(reembed_mod, "SessionLocal", Session)
        monkeypatch.setattr(reembed_mod, "embed_texts", _fake_embed)
        yield Session
        engine.dispose()
    finally:
        with psycopg.connect(_admin_conninfo(base), autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _seed_doc(Session: sessionmaker, n_chunks: int) -> uuid.UUID:
    """Create a user/KB/document with n embedded chunks at the base dimension."""
    with Session() as db:
        user = User(email=f"u{uuid.uuid4().hex[:8]}@t.co", hashed_password="x")
        db.add(user)
        db.flush()
        kb = KnowledgeBase(name="KB", owner_user_id=user.id)
        db.add(kb)
        db.flush()
        doc = Document(
            kb_id=kb.id, filename="d.txt", content_type="text/plain",
            status=DocumentStatus.ready, chunk_count=n_chunks,
        )
        db.add(doc)
        db.flush()
        for i in range(n_chunks):
            db.add(Chunk(
                kb_id=kb.id, document_id=doc.id, chunk_index=i,
                content=f"chunk-{i}", embedding=[0.5] * _BASE_DIM,
            ))
        db.commit()
        return doc.id


def _column_dim(db) -> int:
    return db.execute(
        text("SELECT atttypmod FROM pg_attribute "
             "WHERE attrelid='chunks'::regclass AND attname='embedding'")
    ).scalar_one()


def _as_list(embedding) -> list[float]:
    # Reads come back as pgvector HalfVector; normalize to a plain list. 0.5 is
    # exactly representable in half precision, so equality checks stay stable.
    return embedding.to_list() if hasattr(embedding, "to_list") else list(embedding)


def test_full_switch_with_dimension_change(
    temp_db: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_doc(temp_db, n_chunks=5)
    monkeypatch.setattr(settings, "embedding_model", "tiny/model")
    monkeypatch.setattr(settings, "embedding_dim", 8)

    assert reembed_mod.reembed(batch_size=2) == 0

    with temp_db() as db:
        assert _column_dim(db) == 8
        cfg = db.scalar(select(EmbeddingConfig))
        assert (cfg.model, cfg.dim) == ("tiny/model", 8)
        assert cfg.pending_model is None and cfg.pending_dim is None
        assert db.scalar(select(func.count()).select_from(Chunk)
                         .where(Chunk.embedding.is_(None))) == 0
        assert db.scalar(select(func.count()).select_from(Document)
                         .where(Document.status == DocumentStatus.ready)) == 1
        # Index rebuilt at the new dimension.
        assert db.execute(text("SELECT 1 FROM pg_indexes "
                               "WHERE indexname='ix_chunks_embedding_hnsw'")).scalar() == 1


def test_model_only_switch_same_dimension(
    temp_db: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_doc(temp_db, n_chunks=3)
    monkeypatch.setattr(settings, "embedding_model", "other/model")  # dim unchanged

    assert reembed_mod.reembed(batch_size=8) == 0

    with temp_db() as db:
        assert _column_dim(db) == _BASE_DIM
        cfg = db.scalar(select(EmbeddingConfig))
        assert cfg.model == "other/model" and cfg.dim == _BASE_DIM
        assert cfg.pending_model is None
        # Vectors were regenerated (first component now encodes text length).
        first = db.scalar(select(Chunk).order_by(Chunk.chunk_index))
        assert _as_list(first.embedding)[0] != 0.5


def test_failure_mid_backfill_is_resumable(
    temp_db: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_doc(temp_db, n_chunks=6)
    monkeypatch.setattr(settings, "embedding_model", "other/model")

    # Fail on the second batch: the first batch is committed, the rest stay NULL.
    calls = {"n": 0}
    real = _fake_embed

    def flaky(texts: list[str]) -> list[list[float]]:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("gateway boom")
        return real(texts)

    monkeypatch.setattr(reembed_mod, "embed_texts", flaky)
    assert reembed_mod.reembed(batch_size=2) == 1  # nonzero exit on failure

    with temp_db() as db:
        cfg = db.scalar(select(EmbeddingConfig))
        # Registry NOT advanced; switch still marked pending -> mismatch persists.
        assert cfg.model == _BASE_MODEL
        assert cfg.pending_model == "other/model"
        null_before = db.scalar(select(func.count()).select_from(Chunk)
                                .where(Chunk.embedding.is_(None)))
        assert null_before > 0
        done = {c.id: _as_list(c.embedding) for c in db.scalars(
            select(Chunk).where(Chunk.embedding.is_not(None))).all()}
        assert done  # first batch survived

    # Resume with a healthy gateway.
    monkeypatch.setattr(reembed_mod, "embed_texts", _fake_embed)
    assert reembed_mod.reembed(batch_size=2) == 0

    with temp_db() as db:
        cfg = db.scalar(select(EmbeddingConfig))
        assert cfg.model == "other/model" and cfg.pending_model is None
        assert db.scalar(select(func.count()).select_from(Chunk)
                         .where(Chunk.embedding.is_(None))) == 0
        # Already-embedded chunks were not re-nulled/rewritten during resume.
        for cid, emb in done.items():
            assert _as_list(db.get(Chunk, cid).embedding) == emb


def test_noop_when_already_matching(temp_db: sessionmaker) -> None:
    _seed_doc(temp_db, n_chunks=2)
    # settings already equal the seeded registry -> nothing to do.
    assert reembed_mod.reembed() == 0
    with temp_db() as db:
        first = db.scalar(select(Chunk).order_by(Chunk.chunk_index))
        assert _as_list(first.embedding) == [0.5] * _BASE_DIM  # untouched
