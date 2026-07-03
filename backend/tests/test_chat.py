"""Tests for the chat-retrieval capability.

Sessions are created from an agent (not a KB list). The grounded-conversation
test exercises the live LLM (tool-calling + answer) and the pgvector retrieval
path end to end, streaming genuine tokens.
"""
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


def _kb_with_doc(client: TestClient, headers: dict[str, str], name: str) -> str:
    kb_id = client.post("/kb", json={"name": name}, headers=headers).json()["id"]
    resp = client.post(
        f"/kb/{kb_id}/documents",
        headers=headers,
        files={"file": ("zephyr.txt", DOC.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 201
    # Ingestion completed (TestClient runs the background task synchronously).
    docs = client.get(f"/kb/{kb_id}/documents", headers=headers).json()
    assert docs[0]["status"] == "ready"
    return kb_id


def _create_agent(
    client: TestClient, headers: dict[str, str], kb_ids: list[str], name: str = "Bot"
) -> str:
    resp = client.post(
        "/agents",
        json={"name": name, "system_prompt": "Answer from the docs.", "kb_ids": kb_ids},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


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


def test_create_session_rejects_inaccessible_agent(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    agent_id = _create_agent(client, alice, [], name="Alice private bot")
    resp = client.post("/chat/sessions", json={"agent_id": agent_id}, headers=bob)
    assert resp.status_code == 403


def test_session_ownership_isolation(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    bob = auth_headers(client, "bob@vng.com.vn")
    agent_id = _create_agent(client, alice, [])
    sid = client.post(
        "/chat/sessions", json={"agent_id": agent_id}, headers=alice
    ).json()["id"]
    # Bob cannot read Alice's session.
    assert client.get(f"/chat/sessions/{sid}/messages", headers=bob).status_code == 404
    # Bob's session list does not include it.
    assert all(s["id"] != sid for s in client.get("/chat/sessions", headers=bob).json())


def test_session_reports_agent(client: TestClient) -> None:
    alice = auth_headers(client, "alice@vng.com.vn")
    agent_id = _create_agent(client, alice, [], name="Named bot")
    s = client.post("/chat/sessions", json={"agent_id": agent_id}, headers=alice).json()
    assert s["agent_id"] == agent_id
    assert s["agent_name"] == "Named bot"


@pytest.mark.live
def test_grounded_conversation_with_citations(client: TestClient) -> None:
    h = auth_headers(client, "alice@vng.com.vn")
    kb_id = _kb_with_doc(client, h, "Zephyr KB")
    agent_id = _create_agent(client, h, [kb_id], name="Zephyr bot")
    sid = client.post(
        "/chat/sessions", json={"agent_id": agent_id, "title": "Zephyr"}, headers=h
    ).json()["id"]

    resp = client.post(
        f"/chat/sessions/{sid}/messages",
        json={"content": "What is the Zephyr access code?"},
        headers=h,
    )
    assert resp.status_code == 200
    answer, citations = _parse_sse(resp.text)
    assert "BLUE-42" in answer
    assert len(citations) >= 1
    assert citations[0]["kb_id"] == kb_id
    assert citations[0]["filename"] == "zephyr.txt"

    # History persisted across the turn.
    history = client.get(f"/chat/sessions/{sid}/messages", headers=h).json()
    assert any(m["role"] == "user" for m in history)
    assert any(m["role"] == "assistant" for m in history)
