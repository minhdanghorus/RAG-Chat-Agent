"""LangGraph agent: retrieval-as-tool chat loop with a Postgres checkpointer.

    START -> agent -> (tool_calls?) -> tools -> agent -> ... -> END

The `retrieve_kb` tool the model sees takes only a `query`; the KB scope comes
from graph state (the session's kb_ids), so the model cannot widen retrieval.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from backend.app.agent.checkpointer import get_checkpointer
from backend.app.agent.llm import get_chat_llm
from backend.app.agent.retrieval import retrieve
from backend.app.db.session import SessionLocal

# Baseline instruction used for seeded "Default Assistant" agents (migration) and
# as a fallback when a session's agent carries no system prompt.
SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions strictly about the user's "
    "documents. Always call the retrieve_kb tool to search the user's knowledge "
    "bases before answering a question about their content. Base your answer only "
    "on the retrieved passages and refer to their sources (e.g. [1], [2]). If the "
    "retrieved passages do not contain the answer, say you don't have enough "
    "grounding in the documents to answer, rather than guessing."
    "Your name is Miku and you are a virtual assistant for the user. You are helpful, kind, and cute."
)


@tool
def retrieve_kb(query: str) -> str:
    """Search the user's selected knowledge bases and return relevant passages.

    Args:
        query: A natural-language search query describing what to find.
    """
    # Body is never executed directly; the tools node performs scoped retrieval.
    return ""


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
    # Per-invocation agent config, populated by chat.py from the session's agent.
    kb_ids: list[str]
    system_prompt: str
    model_name: str
    temperature: float
    retrieval_top_k: int
    retrieval_threshold: float
    citations: list[dict]


def _agent_node(state: ChatState) -> dict:
    llm = get_chat_llm(
        model=state.get("model_name") or None,
        temperature=state.get("temperature", 0.2),
        streaming=True,
    ).bind_tools([retrieve_kb])
    system_prompt = state.get("system_prompt") or SYSTEM_PROMPT
    messages = [SystemMessage(content=system_prompt), *state["messages"]]
    response = llm.invoke(messages)
    return {"messages": [response]}


def _tools_node(state: ChatState) -> dict:
    last = state["messages"][-1]
    kb_ids = [uuid.UUID(x) for x in state.get("kb_ids", [])]
    top_k = state.get("retrieval_top_k", 5)
    threshold = state.get("retrieval_threshold", 0.0)
    tool_messages: list[ToolMessage] = []
    citations: list[dict] = []

    db = SessionLocal()
    try:
        for call in getattr(last, "tool_calls", []):
            if call["name"] != "retrieve_kb":
                continue
            query = call["args"].get("query", "")
            ctx = retrieve(db, kb_ids, query, k=top_k, threshold=threshold)
            citations.extend(ctx.citations)
            tool_messages.append(
                ToolMessage(content=ctx.formatted, tool_call_id=call["id"])
            )
    finally:
        db.close()

    return {"messages": tool_messages, "citations": citations}


def _should_continue(state: ChatState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


@lru_cache
def get_graph():
    builder = StateGraph(ChatState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", _tools_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=get_checkpointer())
