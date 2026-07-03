"""Tests for agent-management: CRUD, grants, KB validation, cross-user retrieval,
and document deletion."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import auth_headers

DOC = (
    "Project Zephyr is an internal initiative. "
    "The Zephyr access code is BLUE-42. "
    "Zephyr launched in March and is led by the platform team."
)


def _kb(client: TestClient, headers: dict[str, str], name: str) -> str:
    return client.post("/kb", json={"name": name}, headers=headers).json()["id"]


def _kb_with_doc(client: TestClient, headers: dict[str, str], name: str) -> str:
    kb_id = _kb(client, headers, name)
    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=headers,
        files={"file": ("zephyr.txt", DOC.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 201
    assert client.get(f"/kb/{kb_id}/documents", headers=headers).json()[0]["status"] == "ready"
    return kb_id


def _parse_sse(text: str) -> tuple[str, list]:
    tokens, citations = [], []
    event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]
            if event == "token":
                tokens.append(json.loads(data)["content"])
            elif event == "citations":
                citations = json.loads(data)
    return "".join(tokens), citations


# --- CRUD & permissions ---
def test_agent_crud_and_defaults(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    kb_id = _kb(client, alice, "A KB")
    created = client.post(
        "/agents",
        json={"name": "Bot", "system_prompt": "Hi", "kb_ids": [kb_id]},
        headers=alice,
    )
    assert created.status_code == 201, created.text
    agent = created.json()
    # Model/retrieval settings default from config.
    assert agent["model_name"]
    assert agent["retrieval_top_k"] == 5
    assert agent["kb_ids"] == [kb_id]

    # Appears in the owner's list.
    listed = client.get("/agents", headers=alice).json()
    assert any(a["id"] == agent["id"] for a in listed)

    # Edit persists.
    upd = client.patch(
        f"/agents/{agent['id']}", json={"name": "Bot v2", "temperature": 0.7}, headers=alice
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "Bot v2"
    assert upd.json()["temperature"] == 0.7


def test_non_owner_cannot_edit_or_delete(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    agent = client.post(
        "/agents", json={"name": "Bot", "system_prompt": "Hi"}, headers=alice
    ).json()
    # Bob has no access at all -> 404 on view; edit/delete forbidden.
    assert client.patch(
        f"/agents/{agent['id']}", json={"name": "X"}, headers=bob
    ).status_code == 403
    assert client.delete(f"/agents/{agent['id']}", headers=bob).status_code == 403


def test_attach_inaccessible_kb_is_rejected(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    alice_kb = _kb(client, alice, "Alice private")
    # Bob cannot attach Alice's KB.
    resp = client.post(
        "/agents",
        json={"name": "Bob bot", "system_prompt": "Hi", "kb_ids": [alice_kb]},
        headers=bob,
    )
    assert resp.status_code == 403


def test_edit_revalidates_kb_set(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    alice_kb = _kb(client, alice, "Alice private 2")
    bob_agent = client.post(
        "/agents", json={"name": "Bob bot", "system_prompt": "Hi"}, headers=bob
    ).json()
    # Editing to include a KB Bob cannot read is rejected.
    resp = client.patch(
        f"/agents/{bob_agent['id']}", json={"kb_ids": [alice_kb]}, headers=bob
    )
    assert resp.status_code == 403


def test_delete_blocked_by_sessions(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    agent = client.post(
        "/agents", json={"name": "Bot", "system_prompt": "Hi"}, headers=alice
    ).json()
    client.post("/chat/sessions", json={"agent_id": agent["id"]}, headers=alice)
    # In use -> 409.
    assert client.delete(f"/agents/{agent['id']}", headers=alice).status_code == 409


# --- Grants ---
def test_grant_and_revoke(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    agent = client.post(
        "/agents", json={"name": "Shared bot", "system_prompt": "Hi"}, headers=alice
    ).json()

    # Grant Bob access.
    g = client.post(
        f"/agents/{agent['id']}/access", json={"email": "bob@vng.com.vn"}, headers=alice
    )
    assert g.status_code == 201
    # Bob now sees the agent and can start a session.
    assert any(a["id"] == agent["id"] for a in client.get("/agents", headers=bob).json())
    assert client.post(
        "/chat/sessions", json={"agent_id": agent["id"]}, headers=bob
    ).status_code == 201

    # Non-owner cannot manage grants.
    assert client.post(
        f"/agents/{agent['id']}/access", json={"email": "carol@vng.com.vn"}, headers=bob
    ).status_code == 403

    # Revoke.
    entries = client.get(f"/agents/{agent['id']}/access", headers=alice).json()
    bob_uid = next(e["user_id"] for e in entries if e["email"] == "bob@vng.com.vn")
    assert client.delete(
        f"/agents/{agent['id']}/access/{bob_uid}", headers=alice
    ).status_code == 204
    assert all(a["id"] != agent["id"] for a in client.get("/agents", headers=bob).json())


# --- Document deletion ---
def test_document_delete_permission_and_cascade(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    kb_id = _kb_with_doc(client, alice, "Deletable KB")
    doc_id = client.get(f"/kb/{kb_id}/documents", headers=alice).json()[0]["id"]

    # Bob cannot see or delete it (KB not accessible -> 404 on the KB path).
    assert client.delete(f"/kb/{kb_id}/documents/{doc_id}", headers=bob).status_code == 404

    # Owner deletes; document disappears.
    assert client.delete(f"/kb/{kb_id}/documents/{doc_id}", headers=alice).status_code == 204
    assert client.get(f"/kb/{kb_id}/documents", headers=alice).json() == []

    # Deleting an unknown doc in the KB -> 404.
    import uuid

    assert client.delete(
        f"/kb/{kb_id}/documents/{uuid.uuid4()}", headers=alice
    ).status_code == 404


# --- Cross-user retrieval through a grant ---
@pytest.mark.live
def test_granted_user_retrieves_from_private_kb(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    # Alice owns the KB + agent; Bob is granted the agent but cannot read the KB.
    kb_id = _kb_with_doc(client, alice, "Alice-only Zephyr")
    agent = client.post(
        "/agents",
        json={"name": "HR bot", "system_prompt": "Answer from the docs.", "kb_ids": [kb_id]},
        headers=alice,
    ).json()
    client.post(
        f"/agents/{agent['id']}/access", json={"email": "bob@vng.com.vn"}, headers=alice
    )

    # Bob cannot open the KB's documents directly.
    assert client.get(f"/kb/{kb_id}/documents", headers=bob).status_code == 404

    # But chatting through the agent retrieves from it.
    sid = client.post(
        "/chat/sessions", json={"agent_id": agent["id"]}, headers=bob
    ).json()["id"]
    resp = client.post(
        f"/chat/sessions/{sid}/messages",
        json={"content": "What is the Zephyr access code?"},
        headers=bob,
    )
    assert resp.status_code == 200
    answer, citations = _parse_sse(resp.text)
    assert "BLUE-42" in answer
    assert any(c["kb_id"] == kb_id for c in citations)
