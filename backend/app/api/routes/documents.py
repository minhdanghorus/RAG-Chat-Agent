"""Document upload and listing routes (nested under a KB)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import select

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.models import Document, DocumentStatus, KnowledgeBase
from backend.app.schemas import DocumentOut
from backend.app.services.access import can_manage_kb, can_read_kb
from backend.app.services.ingestion import ingest_document
from backend.app.services.parsing import is_supported

router = APIRouter(prefix="/kb/{kb_id}/documents", tags=["documents"])


def _load_kb(db: DbSession, current_user: CurrentUser, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or not can_read_kb(db, current_user, kb):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KB not found")
    return kb


@router.get("", response_model=list[DocumentOut])
def list_documents(
    kb_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> list[Document]:
    _load_kb(db, current_user, kb_id)
    return list(
        db.scalars(
            select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at)
        ).all()
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> Document:
    kb = _load_kb(db, current_user, kb_id)
    if not can_manage_kb(db, current_user, kb):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to upload to this KB",
        )
    if not file.filename or not is_supported(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type (allowed: pdf, docx, txt, md)",
        )

    data = await file.read()
    doc = Document(
        kb_id=kb_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.pending,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Ingest asynchronously so the request returns immediately.
    background.add_task(ingest_document, doc.id, file.filename, data)
    return doc
