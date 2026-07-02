"""Tests for the knowledge-base capability (ownership + isolation)."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models import Team
from backend.tests.conftest import auth_headers


def _team_id(name: str) -> str:
    with SessionLocal() as db:
        return str(db.scalar(select(Team.id).where(Team.name == name)))


def test_create_and_list_personal_kb(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")
    resp = client.post("/kb", json={"name": "Alice Personal"}, headers=h)
    assert resp.status_code == 201, resp.text
    kb = resp.json()
    assert kb["owner_user_id"] is not None
    assert kb["owner_team_id"] is None

    listed = client.get("/kb", headers=h).json()
    assert any(k["id"] == kb["id"] for k in listed)


def test_personal_kb_isolated_from_other_user(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    kb = client.post("/kb", json={"name": "Alice Secret"}, headers=alice).json()

    bob_list = client.get("/kb", headers=bob).json()
    assert all(k["id"] != kb["id"] for k in bob_list)

    # Bob cannot fetch it directly (404, not 403 — existence hidden).
    assert client.get(f"/kb/{kb['id']}", headers=bob).status_code == 404


def test_create_team_kb_as_member(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")  # Engineering member
    eng = _team_id("Engineering")
    resp = client.post("/kb", json={"name": "Eng KB", "team_id": eng}, headers=h)
    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_team_id"] == eng

    # Carol (also Engineering) sees it.
    carol = auth_headers(client, "carol@vng.com.vn")
    carol_list = client.get("/kb", headers=carol).json()
    assert any(k["owner_team_id"] == eng for k in carol_list)


def test_create_team_kb_non_member_forbidden(client: TestClient) -> None:
    bob = auth_headers(client, "bob@vng.com.vn")  # Marketing, not Engineering
    eng = _team_id("Engineering")
    resp = client.post("/kb", json={"name": "Sneaky", "team_id": eng}, headers=bob)
    assert resp.status_code == 403


def test_delete_kb_owner_and_non_owner(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    kb = client.post("/kb", json={"name": "To Delete"}, headers=alice).json()

    # Non-owner cannot even see it -> 404.
    assert client.delete(f"/kb/{kb['id']}", headers=bob).status_code == 404
    # Owner deletes.
    assert client.delete(f"/kb/{kb['id']}", headers=alice).status_code == 204
    # Gone.
    assert client.get(f"/kb/{kb['id']}", headers=alice).status_code == 404


def test_get_missing_kb_404(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")
    assert client.get(f"/kb/{uuid.uuid4()}", headers=h).status_code == 404
