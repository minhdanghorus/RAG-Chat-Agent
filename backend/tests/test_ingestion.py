"""Tests for the document-ingestion capability.

Note: these exercise the live Green Node embedding endpoint via the background
task (TestClient runs background tasks before returning the response).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.models import Chunk
from backend.tests.conftest import auth_headers

SAMPLE = (
    "Knowledge bases isolate documents per user and team. "
    "Each chunk is tagged with its kb_id. "
    "Retrieval is filtered by the caller's accessible knowledge bases.\n\n"
    "The agent uses retrieval as its first tool. "
    "Answers are grounded in retrieved chunks and cite their sources."
)


def _make_kb(client: TestClient, headers: dict[str, str], name: str) -> str:
    return client.post("/kb", json={"name": name}, headers=headers).json()["id"]


@pytest.mark.live
def test_upload_and_ingest_txt(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")
    kb_id = _make_kb(client, h, "Ingest KB")

    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=h,
        files={"file": ("notes.txt", SAMPLE.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"

    docs = client.get(f"/kb/{kb_id}/documents", headers=h).json()
    assert len(docs) == 1
    doc = docs[0]
    assert doc["status"] == "ready", doc
    assert doc["chunk_count"] >= 1

    # Chunks carry the kb_id and embeddings of the configured dimension.
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.kb_id == kb_id))
        assert n == doc["chunk_count"]
        dim = db.scalar(
            select(func.vector_dims(Chunk.embedding)).where(Chunk.kb_id == kb_id).limit(1)
        )
        assert dim == settings.embedding_dim


def test_unsupported_file_rejected(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")
    kb_id = _make_kb(client, h, "Reject KB")
    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=h,
        files={"file": ("image.png", b"\x89PNG\r\n", "image/png")},
    )
    assert resp.status_code == 400
    assert client.get(f"/kb/{kb_id}/documents", headers=h).json() == []


def test_upload_to_inaccessible_kb_404(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    kb_id = _make_kb(client, alice, "Alice Only")
    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=bob,
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 404
