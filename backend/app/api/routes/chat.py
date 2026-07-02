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
from backend.app.models import ChatSession
from backend.app.schemas import MessageRequest, SessionCreate, SessionOut
from backend.app.services.access import accessible_kb_ids, resolve_selected_kb_ids

router = APIRouter(prefix="/chat", tags=["chat"])

_REPLAY_CHUNK = 24  # characters per replayed token event


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _load_session(db: DbSession, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate, current_user: CurrentUser, db: DbSession
) -> ChatSession:
    try:
        kb_ids = resolve_selected_kb_ids(db, current_user, payload.kb_ids)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    session = ChatSession(user_id=current_user.id, title=payload.title, kb_ids=kb_ids)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(current_user: CurrentUser, db: DbSession) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.created_at.desc())
        ).all()
    )


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
    # Retrieval gate: session scope intersected with current access.
    allowed = accessible_kb_ids(db, current_user)
    scoped = [kb_id for kb_id in session.kb_ids if kb_id in allowed]

    graph = get_graph()
    config = {"configurable": {"thread_id": str(session_id)}}
    inputs = {
        "messages": [HumanMessage(content=payload.content)],
        "kb_ids": [str(x) for x in scoped],
        "citations": [],
    }

    async def event_stream():
        # Run the (sync) graph to completion on a worker thread (reliable,
        # retriable), then bridge the finished answer + citations back to the
        # async response, replaying the answer as incremental token events.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def worker() -> None:
            try:
                result = graph.invoke(inputs, config)
                answer = ""
                for msg in reversed(result.get("messages", [])):
                    if isinstance(msg, AIMessage) and msg.content:
                        answer = msg.content
                        break
                citations = result.get("citations", [])
                loop.call_soon_threadsafe(queue.put_nowait, ("answer", (answer, citations)))
            except Exception as exc:  # noqa: BLE001 - surface to the client
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

        kind, data = await queue.get()
        if kind == "error":
            yield _sse("error", json.dumps({"detail": data}))
            yield _sse("done", "{}")
            return

        answer, citations = data
        # Replay the answer in small chunks for incremental client rendering.
        for i in range(0, len(answer), _REPLAY_CHUNK):
            yield _sse("token", json.dumps({"content": answer[i : i + _REPLAY_CHUNK]}))
            await asyncio.sleep(0)
        yield _sse("citations", json.dumps(citations))
        yield _sse("done", "{}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
