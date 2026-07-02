"""Chat LLM factory (Green Node / VNG MaaS)."""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.app.core.config import settings


@lru_cache
def get_chat_llm() -> ChatOpenAI:
    # Non-streaming with retries: the gateway intermittently returns 500s, and a
    # non-streaming call is cleanly retriable (a mid-stream abort is not). The
    # completed answer is replayed to the client as incremental SSE tokens, so
    # the streaming UX is preserved without the mid-stream failure mode.
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0.2,
        streaming=False,
        max_retries=2,
        timeout=30,
    )
