"""Scoped retrieval used by the agent's retrieve_kb tool.

Isolation gate: the search is always constrained to the session's kb_ids. The
tool the LLM sees only takes a `query` argument — it cannot widen scope.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models import Document
from backend.app.services.embeddings import embed_query
from backend.app.services.vector_store import vector_store

MAX_SNIPPET = 320


@dataclass
class RetrievedContext:
    formatted: str  # text block fed back to the LLM
    citations: list[dict]  # serializable Citation dicts


def retrieve(
    db: Session,
    kb_ids: list[uuid.UUID],
    query: str,
    k: int = 5,
    threshold: float = 0.0,
) -> RetrievedContext:
    if not kb_ids:
        return RetrievedContext(formatted="No knowledge bases selected.", citations=[])

    qvec = embed_query(query)
    results = vector_store.search(db, kb_ids=kb_ids, query_embedding=qvec, k=k)
    # Drop passages below the agent's similarity threshold (0.0 keeps all).
    if threshold > 0.0:
        results = [r for r in results if r.score >= threshold]
    if not results:
        return RetrievedContext(formatted="No relevant passages found.", citations=[])

    # Resolve filenames for citations in one pass.
    doc_ids = {r.chunk.document_id for r in results}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()}

    lines: list[str] = []
    citations: list[dict] = []
    for i, r in enumerate(results, start=1):
        c = r.chunk
        doc = docs.get(c.document_id)
        filename = doc.filename if doc else "unknown"
        lines.append(f"[{i}] (source: {filename}, chunk {c.chunk_index})\n{c.content}")
        citations.append(
            {
                "document_id": str(c.document_id),
                "kb_id": str(c.kb_id),
                "filename": filename,
                "chunk_index": c.chunk_index,
                "snippet": c.content[:MAX_SNIPPET],
            }
        )
    return RetrievedContext(formatted="\n\n".join(lines), citations=citations)
