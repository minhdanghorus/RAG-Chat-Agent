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

SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions strictly about the user's "
    "documents. Always call the retrieve_kb tool to search the user's knowledge "
    "bases before answering a question about their content. Base your answer only "
    "on the retrieved passages and refer to their sources (e.g. [1], [2]). If the "
    "retrieved passages do not contain the answer, say you don't have enough "
    "grounding in the documents to answer, rather than guessing."
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
    kb_ids: list[str]
    citations: list[dict]


def _agent_node(state: ChatState) -> dict:
    llm = get_chat_llm().bind_tools([retrieve_kb])
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = llm.invoke(messages)
    return {"messages": [response]}


def _tools_node(state: ChatState) -> dict:
    last = state["messages"][-1]
    kb_ids = [uuid.UUID(x) for x in state.get("kb_ids", [])]
    tool_messages: list[ToolMessage] = []
    citations: list[dict] = []

    db = SessionLocal()
    try:
        for call in getattr(last, "tool_calls", []):
            if call["name"] != "retrieve_kb":
                continue
            query = call["args"].get("query", "")
            ctx = retrieve(db, kb_ids, query)
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
