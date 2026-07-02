"""Tests for the user-auth capability."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.tests.conftest import auth_headers


def test_login_success(client: TestClient) -> None:
    resp = client.post(
        "/auth/login", json={"email": "alice@vng.com.vn", "password": "password123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client: TestClient) -> None:
    resp = client.post(
        "/auth/login", json={"email": "alice@vng.com.vn", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_login_unknown_user(client: TestClient) -> None:
    resp = client.post(
        "/auth/login", json={"email": "nobody@vng.com.vn", "password": "password123"}
    )
    assert resp.status_code == 401


def test_me_requires_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_invalid_token(client: TestClient) -> None:
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_me_with_token(client: TestClient) -> None:
    resp = client.get("/auth/me", headers=auth_headers(client, "alice@vng.com.vn"))
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@vng.com.vn"
