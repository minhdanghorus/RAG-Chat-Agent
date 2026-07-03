## Why

Users need a way to upload their own documents and have grounded, cited conversations about them, with strict isolation so each user (and their team/department) only ever sees their own knowledge. This MVP establishes that RAG loop on a foundation that can grow into a tool-using agent (MCP/other systems) without a rewrite — hence "agent," not "chatbot."

## What Changes

- Introduce a **FastAPI + LangGraph** backend that serves a token-authenticated API for auth, knowledge-base management, document upload/ingestion, and streaming chat.
- Introduce **Knowledge Bases (KBs)** as the unit of access and retrieval. A KB is owned by a user (personal) or a team (shared). Documents and their chunks belong to a KB; `kb_id` is the isolation key on every chunk.
- Enforce **two-gate isolation**: an authorization gate resolves the KBs a user may access; a retrieval gate filters every vector search by the allowed-and-selected `kb_id` set.
- Add a **document ingestion pipeline**: parse (pdf/docx/txt) → chunk → embed via Green Node → store chunks with embeddings in Postgres/pgvector.
- Add an **agent chat loop** in LangGraph where retrieval is the first tool (`retrieve_kb`), scoped to the user's selected KBs, returning answers with **source citations** and **token streaming**. Conversation history is **persisted** via a Postgres checkpointer.
- Add a **Next.js/React frontend**: login, KB list/create/upload, per-chat KB picker, streaming chat with inline citations.
- Add **infrastructure**: swap the existing Docker Postgres image to `pgvector/pgvector:pg18` to enable the `vector` extension; relax `requires-python` to `>=3.12`.
- Users and teams are **seeded/admin-created** for the MVP (no self-signup), but passwords are hashed and identity is carried by **JWT from day one** so self-signup/SSO is an additive change later.

## Capabilities

### New Capabilities
- `user-auth`: Identity for the platform — seeded users and teams, team membership, password hashing, JWT issuance/verification, and the authenticated-request contract.
- `knowledge-base`: KB lifecycle (create/list/delete), personal vs team ownership, access resolution, and the authorization gate that determines which KBs a user may read or manage.
- `document-ingestion`: Uploading documents into a KB and turning them into retrievable, embedded chunks (parse → chunk → embed → store), with per-document status.
- `chat-retrieval`: The agent chat loop — KB selection per chat, isolation-enforced retrieval as a tool, streamed answers with citations, and persisted conversation history.

### Modified Capabilities
<!-- None — this is the first change; no existing specs. -->

## Impact

- **New code**: `backend/` (FastAPI app, LangGraph agent, ingestion, DB models/migrations, auth), `frontend/` (Next.js app).
- **Dependencies (backend)**: fastapi, uvicorn, sqlalchemy, psycopg, pgvector, langchain, langgraph, langgraph-checkpoint-postgres, langchain-openai, pypdf, python-docx, python-jose/passlib (JWT + hashing), pydantic-settings, python-dotenv.
- **Dependencies (frontend)**: next, react (chat UI + SSE streaming client).
- **Infra**: `D:\postgres_sql\compose.yml` — `vng_db` image `postgres:18.0` → `pgvector/pgvector:pg18`; DB reachable at `localhost:5433`, user `openerp8`, db `postgres`. Requires `CREATE EXTENSION vector;` once.
- **Config**: `.env` with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, embedding model name, `DATABASE_URL`, `JWT_SECRET` (reuses the Green Node env pattern from the existing LangChain work).
- **Project**: `pyproject.toml` `requires-python` `>=3.13` → `>=3.12`; reconcile `.python-version` (3.12.3).
