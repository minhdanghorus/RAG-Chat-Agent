"""Embedding client backed by the Green Node (VNG MaaS) gateway."""
from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from backend.app.core.config import settings

_BATCH = 64


@lru_cache
def _client() -> OpenAIEmbeddings:
    # check_embedding_ctx_length=False sends text as-is (the default path uses
    # tiktoken token-splitting tuned for OpenAI models, which misbehaves here).
    return OpenAIEmbeddings(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.embedding_model,
        check_embedding_ctx_length=False,
        max_retries=3,
        timeout=60,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed documents in batches. Returns one vector per input text."""
    client = _client()
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        out.extend(client.embed_documents(texts[i : i + _BATCH]))
    return out


def embed_query(text: str) -> list[float]:
    return _client().embed_query(text)
