"""Vector store abstraction and pgvector implementation.

Retrieval sits behind this interface so a future swap (e.g. Qdrant) is a
contained change. The pgvector implementation is the authoritative retrieval
gate: every search is filtered by kb_id.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Chunk


@dataclass
class SearchResult:
    chunk: Chunk
    score: float  # cosine similarity in [0, 1] (higher = closer)


class VectorStore(ABC):
    @abstractmethod
    def add_chunks(
        self,
        db: Session,
        *,
        kb_id: uuid.UUID,
        document_id: uuid.UUID,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
    ) -> int: ...

    @abstractmethod
    def search(
        self,
        db: Session,
        *,
        kb_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int = 5,
    ) -> list[SearchResult]: ...


class PgVectorStore(VectorStore):
    def add_chunks(
        self,
        db: Session,
        *,
        kb_id: uuid.UUID,
        document_id: uuid.UUID,
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        rows = [
            Chunk(
                kb_id=kb_id,
                document_id=document_id,
                chunk_index=i,
                content=text,
                embedding=list(emb),
            )
            for i, (text, emb) in enumerate(zip(texts, embeddings, strict=True))
        ]
        db.add_all(rows)
        db.flush()
        return len(rows)

    def search(
        self,
        db: Session,
        *,
        kb_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int = 5,
    ) -> list[SearchResult]:
        # Empty scope -> nothing is searchable (isolation-safe default).
        if not kb_ids:
            return []
        distance = Chunk.embedding.cosine_distance(list(query_embedding))
        stmt = (
            select(Chunk, distance.label("distance"))
            .where(Chunk.kb_id.in_(list(kb_ids)))
            # Skip chunks awaiting re-embedding (NULL embedding) so a switch in
            # progress degrades to partial/empty results instead of erroring.
            .where(Chunk.embedding.isnot(None))
            .order_by(distance)
            .limit(k)
        )
        results = db.execute(stmt).all()
        return [SearchResult(chunk=row[0], score=1.0 - float(row[1])) for row in results]


# Default store used across the app.
vector_store: VectorStore = PgVectorStore()
