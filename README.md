# RAG Chat Agent

An MVP RAG platform: users upload documents into **knowledge bases** and chat with an
agent grounded in those documents, with strict **per-user / per-team isolation**. Built
so it can grow into a tool/MCP-using agent — retrieval is the agent's first tool.

- **Backend:** FastAPI + LangGraph (retrieval-as-tool agent loop)
- **Data:** Postgres 18 + pgvector (`halfvec` embeddings, HNSW cosine index; dimension
  tracks the configured embedding model) — one store for RBAC, vectors, and conversation
  history (LangGraph Postgres checkpointer)
- **LLM/embeddings:** Green Node (VNG MaaS), OpenAI-compatible
- **Frontend:** Next.js / React (login, KB management, streaming chat with citations)

## Architecture

```
Next.js (React) ──JWT──▶ FastAPI ──▶ Postgres + pgvector
  login, KB upload,        auth / kb / documents / chat (SSE)      RBAC + chunks + checkpoints
  streaming chat                    │
                                    ▼
                          LangGraph agent: agent ⇄ retrieve_kb tool
                                    │  (scope = session KBs ∩ user's accessible KBs)
                                    ▼
                          Green Node (chat + embeddings)
```

**Two-gate isolation:** (1) an authorization gate resolves the KBs a user may access
(personal ∪ team); (2) every retrieval is filtered to `session KBs ∩ accessible KBs`.
The `retrieve_kb` tool exposes only a `query` argument, so the model cannot widen scope.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12+)
- Docker Desktop
- Node.js 20+ (for the frontend)

## Setup

### 1. Database (Docker)

A dedicated pgvector container (isolated from any other Postgres you run):

```bash
docker compose up -d rag_db
```

This starts Postgres 18 + pgvector on host port **5434** (db `rag_chat`, user `rag`).

### 2. Backend

```bash
uv sync                                   # install dependencies
cp .env.example .env                      # then fill in LLM_API_KEY etc.
uv run alembic upgrade head               # create schema (tables + HNSW index)
uv run python -m backend.scripts.seed     # seed sample users + teams
uv run uvicorn backend.app.main:app --reload --port 8000
```

Seeded logins (password `password123`): `alice@vng.com.vn` (Engineering),
`bob@vng.com.vn` (Marketing), `carol@vng.com.vn` (both). API docs at
http://localhost:8000/docs.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

`frontend/.env.local` points at the backend via `NEXT_PUBLIC_API_BASE`
(default `http://localhost:8000`).

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` | Green Node gateway (OpenAI-compatible) |
| `LLM_MODEL` | Chat model (default `google/gemma-4-31b-it`) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | Active embedding model + its vector dimension (e.g. `gemini/gemini-embedding-001`, `3072` or `baai/bge-m3`, `1024`) |
| `DATABASE_URL` | `postgresql+psycopg://rag:rag_password@localhost:5434/rag_chat` |
| `JWT_SECRET` | Signing key for access tokens |
| `CORS_ORIGINS` | Allowed frontend origins |

### Switching the embedding model

Stored embeddings are **model- and dimension-specific** — vectors from different
models (or dimensions) cannot be compared, and pgvector's column/index is fixed to
one dimension. So changing `EMBEDDING_MODEL` / `EMBEDDING_DIM` is not a pure config
change. The database records the model that produced its vectors (`embedding_config`
registry) and validates it against your settings:

- On a mismatch, the **app refuses to start** and document **uploads return HTTP 409**,
  each naming the configured vs. registered model and the remedy below.

To switch:

```bash
# 1. Edit .env: set EMBEDDING_MODEL / EMBEDDING_DIM to the new model
# 2. Re-embed existing chunks from their stored text and update the registry:
uv run python -m backend.app.cli reembed
```

`reembed` re-embeds every chunk from the `content` already in Postgres (no re-upload
needed for a pure model swap), rebuilds the HNSW index, and is **idempotent/resumable**
— if it is interrupted, just run it again. While it runs, retrieval degrades gracefully
(chunks pending re-embed are skipped) rather than erroring. Changing chunking (not just
the model) still requires re-uploading the documents.

## Testing

```bash
uv run pytest              # deterministic suite (no external calls)
uv run pytest -m live      # integration tests that hit the LLM gateway (opt-in)
```

The `live` tests are opt-in because the gateway is non-deterministic; the default
suite covers auth, KB isolation, ingestion permissions, and the retrieval gate.

## Notes on streaming reliability

The Green Node gateway can intermittently 500 or hang mid-stream, and mid-stream
aborts aren't retriable. The chat LLM therefore runs **non-streaming with retries**
inside the graph, and the completed answer is **replayed to the client as incremental
SSE tokens** — preserving the streaming UX without the mid-stream failure mode.

## Project layout

```
backend/
  app/
    core/       config, security (JWT + hashing)
    db/         SQLAlchemy engine/session
    models/     ORM models (users, teams, KBs, documents, chunks, sessions)
    api/        deps + routes (auth, kb, documents, chat)
    services/   access control, embeddings, parsing, chunking, vector_store, ingestion
    agent/      llm, retrieval, graph (LangGraph), checkpointer
  alembic/      migrations
  scripts/      seed.py
  tests/        pytest suite
frontend/       Next.js app (login, kb, chat)
docker-compose.yml   dedicated pgvector database
openspec/       change proposal + specs (add-rag-mvp)
```

## Deferred (phase 2)

Multimodal/scanned-document ingestion, admin-defined agents bound to KBs,
self-signup / SSO, additional tools / MCP integration, hybrid search.
