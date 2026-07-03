"""Chat routes: sessions and streaming messages."""
from __future__ import annotations

import asyncio
import json
import threading
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select

from backend.app.agent.graph import get_graph
from backend.app.api.deps import CurrentUser, DbSession
from backend.app.models import Agent, ChatSession
from backend.app.schemas import MessageRequest, SessionCreate, SessionOut
from backend.app.services.access import can_use_agent

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _load_session(db: DbSession, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


def _session_out(db: DbSession, session: ChatSession) -> SessionOut:
    agent_name = None
    if session.agent_id is not None:
        agent = db.get(Agent, session.agent_id)
        agent_name = agent.name if agent else None
    return SessionOut(
        id=session.id,
        title=session.title,
        agent_id=session.agent_id,
        agent_name=agent_name,
        created_at=session.created_at,
    )


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate, current_user: CurrentUser, db: DbSession
) -> SessionOut:
    agent = db.get(Agent, payload.agent_id)
    if agent is None or not can_use_agent(db, current_user, agent):
        # 403 for an agent the user cannot use (existence not otherwise revealed).
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Agent not accessible"
        )
    session = ChatSession(
        user_id=current_user.id, title=payload.title, agent_id=agent.id
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(current_user: CurrentUser, db: DbSession) -> list[SessionOut]:
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return [_session_out(db, s) for s in sessions]


@router.get("/sessions/{session_id}/messages")
def get_history(
    session_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> list[dict]:
    _load_session(db, current_user.id, session_id)
    graph = get_graph()
    config = {"configurable": {"thread_id": str(session_id)}}
    state = graph.get_state(config)
    messages = state.values.get("messages", []) if state.values else []
    out: list[dict] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage) and m.content:
            out.append({"role": "assistant", "content": m.content})
    return out


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    payload: MessageRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> StreamingResponse:
    session = _load_session(db, current_user.id, session_id)
    agent = db.get(Agent, session.agent_id) if session.agent_id else None
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session has no agent; start a new chat",
        )

    # Retrieval scope is the agent's stored KBs as-is (agent access confers
    # retrieval access — no intersection with the chatting user's KB access).
    graph = get_graph()
    config = {"configurable": {"thread_id": str(session_id)}}
    inputs = {
        "messages": [HumanMessage(content=payload.content)],
        "kb_ids": [str(x) for x in agent.kb_ids],
        "system_prompt": agent.system_prompt,
        "model_name": agent.model_name,
        "temperature": agent.temperature,
        "retrieval_top_k": agent.retrieval_top_k,
        "retrieval_threshold": agent.retrieval_threshold,
        "citations": [],
    }

    async def event_stream():
        # Real token streaming: run the (sync) graph with stream_mode="messages"
        # on a worker thread and bridge genuine LLM tokens to the async response
        # as they are generated. The graph's checkpointer is sync-only, so a
        # worker thread (not astream) is the supported path; unlike the old
        # replay bridge, tokens are forwarded while the model is still generating.
        # Only agent-node tokens are forwarded (tool-call deltas / ToolMessages
        # are skipped).
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def worker() -> None:
            try:
                for chunk, metadata in graph.stream(
                    inputs, config, stream_mode="messages"
                ):
                    if metadata.get("langgraph_node") != "agent":
                        continue
                    text = getattr(chunk, "content", None)
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, ("token", text))
                loop.call_soon_threadsafe(queue.put_nowait, ("end", None))
            except Exception as exc:  # noqa: BLE001 - surface to the client
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

        while True:
            kind, data = await queue.get()
            if kind == "token":
                yield _sse("token", json.dumps({"content": data}))
            elif kind == "error":
                yield _sse("error", json.dumps({"detail": data}))
                yield _sse("done", "{}")
                return
            else:  # "end"
                break

        # Citations come from the final graph state after generation completes.
        state = graph.get_state(config)
        citations = state.values.get("citations", []) if state.values else []
        yield _sse("citations", json.dumps(citations))
        yield _sse("done", "{}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
