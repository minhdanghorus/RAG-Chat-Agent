"""Deterministic tests for the retrieval isolation gate (no external calls).

Chunks are inserted with hand-made embedding vectors so retrieval behaviour is
fully deterministic and independent of the LLM gateway.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from backend.app.agent.graph import retrieve_kb
from backend.app.agent.retrieval import retrieve
from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models import Chunk, Document, DocumentStatus, KnowledgeBase, User
from backend.app.services.vector_store import vector_store

DIM = settings.embedding_dim


def _unit_vec(hot: int) -> list[float]:
    v = [0.0] * DIM
    v[hot] = 1.0
    return v


def _make_kb_with_chunk(db, owner_id: uuid.UUID, name: str, text: str, hot: int):
    kb = KnowledgeBase(name=name, owner_user_id=owner_id)
    db.add(kb)
    db.flush()
    doc = Document(
        kb_id=kb.id, filename=f"{name}.txt", content_type="text/plain",
        status=DocumentStatus.ready,
    )
    db.add(doc)
    db.flush()
    vector_store.add_chunks(
        db, kb_id=kb.id, document_id=doc.id, texts=[text], embeddings=[_unit_vec(hot)]
    )
    db.commit()
    return kb


def test_search_is_scoped_to_kb_ids() -> None:
    with SessionLocal() as db:
        alice = db.scalar(select(User).where(User.email == "alice@vng.com.vn"))
        kb_a = _make_kb_with_chunk(db, alice.id, f"A-{uuid.uuid4().hex[:6]}", "alpha content", 0)
        kb_b = _make_kb_with_chunk(db, alice.id, f"B-{uuid.uuid4().hex[:6]}", "beta content", 1)

        # Query vector closest to kb_a's chunk.
        q = _unit_vec(0)
        res_a = vector_store.search(db, kb_ids=[kb_a.id], query_embedding=q, k=5)
        assert res_a and all(r.chunk.kb_id == kb_a.id for r in res_a)

        # Scoped to kb_b only -> never returns kb_a's chunk even for the same query.
        res_b = vector_store.search(db, kb_ids=[kb_b.id], query_embedding=q, k=5)
        assert all(r.chunk.kb_id == kb_b.id for r in res_b)

        # Empty scope -> nothing (isolation-safe default).
        assert vector_store.search(db, kb_ids=[], query_embedding=q, k=5) == []


@pytest.mark.live
def test_retrieve_citations_scoped() -> None:
    with SessionLocal() as db:
        alice = db.scalar(select(User).where(User.email == "alice@vng.com.vn"))
        kb = _make_kb_with_chunk(db, alice.id, f"C-{uuid.uuid4().hex[:6]}", "gamma secret", 2)
        # retrieve() embeds the query via the gateway; use a query that will match.
        ctx = retrieve(db, [kb.id], "gamma", k=3)
        assert ctx.citations
        assert all(c["kb_id"] == str(kb.id) for c in ctx.citations)


def test_search_skips_null_embeddings() -> None:
    """Chunks awaiting re-embedding (NULL embedding) must not be returned, and a
    scope containing only such chunks yields an empty result rather than an error.

    Cleans up its KBs so no NULL-embedding rows leak into the shared dev DB.
    """
    with SessionLocal() as db:
        alice = db.scalar(select(User).where(User.email == "alice@vng.com.vn"))
        kb = KnowledgeBase(name=f"N-{uuid.uuid4().hex[:6]}", owner_user_id=alice.id)
        kb_empty = KnowledgeBase(name=f"NE-{uuid.uuid4().hex[:6]}", owner_user_id=alice.id)
        db.add_all([kb, kb_empty])
        db.flush()
        try:
            doc = Document(
                kb_id=kb.id, filename="n.txt", content_type="text/plain",
                status=DocumentStatus.processing,
            )
            db.add(doc)
            db.flush()
            # One embedded chunk, one still pending (NULL embedding).
            db.add(Chunk(kb_id=kb.id, document_id=doc.id, chunk_index=0,
                         content="embedded", embedding=_unit_vec(0)))
            db.add(Chunk(kb_id=kb.id, document_id=doc.id, chunk_index=1,
                         content="pending", embedding=None))

            doc2 = Document(kb_id=kb_empty.id, filename="e.txt", content_type="text/plain",
                            status=DocumentStatus.processing)
            db.add(doc2)
            db.flush()
            db.add(Chunk(kb_id=kb_empty.id, document_id=doc2.id, chunk_index=0,
                         content="pending only", embedding=None))
            db.commit()

            q = _unit_vec(0)
            res = vector_store.search(db, kb_ids=[kb.id], query_embedding=q, k=5)
            assert res, "the embedded chunk should be retrievable"
            assert all(r.chunk.embedding is not None for r in res)
            assert all(r.chunk.content != "pending" for r in res)

            # A KB whose only chunk is pending returns nothing (no error).
            assert vector_store.search(db, kb_ids=[kb_empty.id], query_embedding=q, k=5) == []
        finally:
            db.rollback()
            db.delete(db.get(KnowledgeBase, kb.id))  # cascades to docs/chunks
            db.delete(db.get(KnowledgeBase, kb_empty.id))
            db.commit()


def test_retrieve_tool_cannot_widen_scope() -> None:
    # The tool the model sees exposes only `query` — no kb_id argument — so a
    # model cannot widen retrieval beyond the session's scope.
    schema = retrieve_kb.args_schema.model_json_schema()
    assert set(schema["properties"].keys()) == {"query"}
