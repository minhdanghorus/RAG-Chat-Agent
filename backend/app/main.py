"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import agents, auth, chat, documents, kb
from backend.app.core.config import settings
from backend.app.db.session import SessionLocal
from backend.app.services.embedding_config import check_settings_match


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail fast if the configured embedding model disagrees with the database.

    Stored vectors are model- and dimension-specific; serving with a mismatched
    configuration would corrupt ingestion and retrieval. Refuse to start and
    point the operator at the reembed command.
    """
    with SessionLocal() as db:
        mismatch = check_settings_match(db)
    if mismatch is not None:
        raise RuntimeError(mismatch.message)
    yield


app = FastAPI(title="RAG Chat Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(documents.router)
app.include_router(agents.router)
app.include_router(chat.router)
