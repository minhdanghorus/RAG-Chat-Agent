"""Chat LLM factory (Green Node / VNG MaaS).

Parameterized per agent (model + temperature) so each agent can carry its own
model settings, with a cache keyed by the full config. Chat uses streaming so
genuine LLM tokens can be forwarded to the client via astream.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.app.core.config import settings


@lru_cache
def get_chat_llm(
    model: str | None = None,
    temperature: float = 0.2,
    streaming: bool = True,
) -> ChatOpenAI:
    # Streaming is enabled so astream(stream_mode="messages") yields real tokens.
    # Retries still cover the gateway's intermittent 500s on connect.
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=model or settings.llm_model,
        temperature=temperature,
        streaming=streaming,
        max_retries=2,
        timeout=30,
    )
