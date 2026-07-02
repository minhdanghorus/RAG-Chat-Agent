"""Shared test fixtures.

Tests run against the local dev database (docker rag_chat_db). The schema must
be migrated (`uv run alembic upgrade head`) and seeded before running.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.scripts.seed import DEFAULT_PASSWORD, main as seed_main


@pytest.fixture(scope="session", autouse=True)
def _seed() -> None:
    seed_main()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def login(client: TestClient, email: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": DEFAULT_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {login(client, email)}"}
