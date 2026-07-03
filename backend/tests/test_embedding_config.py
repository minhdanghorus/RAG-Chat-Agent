"""Tests for embedding-configuration validation (registry vs. settings).

These run against the shared dev database, which is expected to be consistent
(registry matches settings) before the suite runs. Mismatch scenarios are
simulated by monkeypatching the validation seam or by temporarily mutating the
single registry row and restoring it, so no destructive state leaks.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.services import embedding_config as ec
from backend.app.services.embedding_config import (
    ConfigMismatch,
    check_settings_match,
    get_active_config,
)
from backend.tests.conftest import auth_headers


def test_registry_matches_settings_by_default() -> None:
    with SessionLocal() as db:
        assert check_settings_match(db) is None


def test_dimension_mismatch_detected() -> None:
    with SessionLocal() as db:
        cfg = get_active_config(db)
        original_dim = cfg.dim
        cfg.dim = original_dim + 1  # force a dimension disagreement
        db.flush()
        try:
            mismatch = check_settings_match(db)
            assert mismatch is not None
            assert mismatch.configured_dim == settings.embedding_dim
            assert mismatch.active_dim == original_dim + 1
            assert ec.REEMBED_COMMAND in mismatch.message
        finally:
            db.rollback()


def test_same_dimension_different_model_detected() -> None:
    """A different model of equal dimension must still count as a mismatch."""
    with SessionLocal() as db:
        cfg = get_active_config(db)
        cfg.model = settings.embedding_model + "-other"  # same dim, different model
        db.flush()
        try:
            mismatch = check_settings_match(db)
            assert mismatch is not None
            assert mismatch.active_dim == settings.embedding_dim
            assert mismatch.configured_model == settings.embedding_model
        finally:
            db.rollback()


def test_startup_ok_when_config_matches() -> None:
    # Lifespan runs on context-manager entry; a matching config starts cleanly.
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_startup_fails_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    mismatch = ConfigMismatch(
        configured_model="baai/bge-m3",
        configured_dim=1024,
        active_model="gemini/gemini-embedding-001",
        active_dim=3072,
    )
    monkeypatch.setattr("backend.app.main.check_settings_match", lambda db: mismatch)
    with pytest.raises(RuntimeError, match="Embedding configuration mismatch"):
        with TestClient(app):
            pass


def test_ingestion_rejected_on_mismatch_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mismatch = ConfigMismatch(
        configured_model="baai/bge-m3",
        configured_dim=1024,
        active_model="gemini/gemini-embedding-001",
        active_dim=3072,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.documents.check_settings_match", lambda db: mismatch
    )
    h = auth_headers(client, "alice@vng.com.vn")
    kb_id = client.post("/kb", json={"name": "Mismatch KB"}, headers=h).json()["id"]
    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=h,
        files={"file": ("x.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 409, resp.text
    assert ec.REEMBED_COMMAND in resp.json()["detail"]
    # No document record was created (rejected before ingestion).
    assert client.get(f"/kb/{kb_id}/documents", headers=h).json() == []
