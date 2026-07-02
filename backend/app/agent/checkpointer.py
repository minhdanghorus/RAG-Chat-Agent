"""LangGraph Postgres checkpointer (persisted conversation history)."""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.app.core.config import settings


def _conn_string() -> str:
    # PostgresSaver uses psycopg directly, so strip the SQLAlchemy driver suffix.
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_checkpointer() -> PostgresSaver:
    pool = ConnectionPool(
        conninfo=_conn_string(),
        max_size=10,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    saver = PostgresSaver(pool)
    saver.setup()  # idempotent: creates checkpoint tables if absent
    return saver
