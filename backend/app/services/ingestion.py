"""Document ingestion: parse -> chunk -> embed -> store, with status tracking."""
from __future__ import annotations

import uuid

from backend.app.db.session import SessionLocal
from backend.app.models import Document, DocumentStatus
from backend.app.services.chunking import chunk_text
from backend.app.services.embeddings import embed_texts
from backend.app.services.parsing import extract_text
from backend.app.services.vector_store import vector_store


def ingest_document(document_id: uuid.UUID, filename: str, data: bytes) -> None:
    """Full ingestion pipeline for one document.

    Runs in a background task with its own DB session. Updates the document's
    status to processing -> ready, or failed (recording the error).
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = DocumentStatus.processing
        db.commit()

        text = extract_text(filename, data)
        chunks = chunk_text(text)
        if not chunks:
            doc.status = DocumentStatus.failed
            doc.error = "No extractable text found in document."
            db.commit()
            return

        embeddings = embed_texts(chunks)
        count = vector_store.add_chunks(
            db,
            kb_id=doc.kb_id,
            document_id=doc.id,
            texts=chunks,
            embeddings=embeddings,
        )
        doc.chunk_count = count
        doc.status = DocumentStatus.ready
        db.commit()
    except Exception as exc:  # noqa: BLE001 - record any failure on the document
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.failed
            doc.error = str(exc)[:2000]
            db.commit()
    finally:
        db.close()
