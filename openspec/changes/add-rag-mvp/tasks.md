## 1. Infrastructure & Project Setup

- [x] 1.1 (Superseded) Existing cluster hosts a 10GB Odoo/ERP DB — too risky to swap its image; use a dedicated container instead (see 1.2)
- [x] 1.2 Create dedicated `docker-compose.yml` with `pgvector/pgvector:pg18` (service `rag_db`, host port 5434, db `rag_chat`); `docker compose up -d rag_db`
- [x] 1.3 Enable extension: `CREATE EXTENSION IF NOT EXISTS vector;` (pgvector 0.8.4, `halfvec` verified)
- [x] 1.4 Relax `pyproject.toml` `requires-python` to `>=3.12` and reconcile `.python-version`
- [x] 1.5 Add backend dependencies via `uv`: fastapi, uvicorn, sqlalchemy, psycopg[binary], pgvector, langchain, langgraph, langgraph-checkpoint-postgres, langchain-openai, pypdf, python-docx, passlib[bcrypt], python-jose[cryptography], pydantic-settings, python-dotenv
- [x] 1.6 Create `.env` (git-ignored) with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `DATABASE_URL` (localhost:5433), `JWT_SECRET`; add `settings.py` (pydantic-settings)
- [x] 1.7 Establish `backend/` package layout (app, api, core/config, db, models, services, agent) and a runnable `uvicorn` entrypoint

## 2. Data Model & Migrations

- [x] 2.1 Define SQLAlchemy models: `users`, `teams`, `memberships`, `knowledge_bases` (owner_user_id | owner_team_id), `documents`, `chunks`
- [x] 2.2 Add `chunks.embedding halfvec(3072)` (gemini-embedding-001) with an HNSW index `(embedding halfvec_cosine_ops)`
- [x] 2.3 Add migrations (Alembic) and create the schema against the pgvector DB
- [x] 2.4 Write a seed script that creates sample teams, users (hashed passwords), and memberships

## 3. Auth (capability: user-auth)

- [x] 3.1 Password hashing (passlib) and verification helpers
- [x] 3.2 `POST /auth/login`: verify credentials, issue signed JWT with user id + expiry
- [x] 3.3 JWT verification dependency that resolves the caller's user id and team memberships; reject invalid/expired tokens with 401
- [x] 3.4 Tests for: successful login, wrong credentials, missing/invalid token, valid token resolves identity

## 4. Knowledge Bases (capability: knowledge-base)

- [x] 4.1 Access-set resolver: given a user, return personal KBs ∪ team KBs (single source of truth)
- [x] 4.2 `POST /kb` create (personal or team; reject team KB if not a member), `GET /kb` list (accessible only), `DELETE /kb/{id}` (owner/owning-team member only, cascade documents+chunks)
- [x] 4.3 Manage-permission check reused by upload and delete
- [x] 4.4 Tests for: create personal/team, forbidden team create, list isolation, owner delete, non-owner delete forbidden

## 5. Ingestion (capability: document-ingestion)

- [x] 5.1 `VectorStore` interface + pgvector implementation (insert chunks, similarity search with `kb_id` filter)
- [x] 5.2 Parsers for PDF (pypdf), DOCX (python-docx), TXT; reject unsupported types
- [x] 5.3 Chunker (configurable size/overlap) producing positional metadata
- [x] 5.4 Embedding client via `OpenAIEmbeddings` (Green Node, `gemini/gemini-embedding-001`), batched; store as `halfvec(3072)`; validate dimension = 3072
- [x] 5.5 `POST /kb/{id}/documents` upload (manage-permission gated) → create document "pending" → async ingest → chunks stored with `kb_id`, doc ref, embedding → status "ready"/"failed"
- [x] 5.6 `GET /kb/{id}/documents` list with status
- [x] 5.7 Tests for: supported upload creates chunks with `kb_id`, unsupported rejected, upload without manage forbidden, status transitions, dimension consistency

## 6. Agent Chat & Retrieval (capability: chat-retrieval)

- [x] 6.1 `retrieve_kb` tool: embed query, similarity search filtered to `session_kbs ∩ caller_access_set`; ignore out-of-scope kb targets; return chunks + source refs
- [x] 6.2 LangGraph `StateGraph`: agent(LLM) ↔ retrieve_kb tool → END; wire Green Node `ChatOpenAI`
- [x] 6.3 Configure Postgres checkpointer (`langgraph-checkpoint-postgres`) for per-session history
- [x] 6.4 `POST /chat/sessions` create session bound to selected accessible KBs (reject inaccessible)
- [x] 6.5 `POST /chat/sessions/{id}/messages` (SSE streaming) → run graph, stream tokens, return citations; "no grounding" response when retrieval is empty
- [x] 6.6 `GET /chat/sessions` and `GET /chat/sessions/{id}` scoped to the caller
- [x] 6.7 Tests for: KB selection scoping, inaccessible KB rejected, retrieval not widenable by tool args, answer includes citations, no-context path, history persists+reload, session ownership scoping

## 7. Frontend (Next.js/React)

- [x] 7.1 Scaffold Next.js app; API client with JWT storage/attachment
- [x] 7.2 Login page (seeded users)
- [x] 7.3 KB list + create + document upload (with ingestion status display)
- [x] 7.4 Chat page: per-chat KB picker, streaming responses (SSE), inline source citations
- [x] 7.5 Session list / reload prior conversations

## 8. Verification & Docs

- [x] 8.1 End-to-end smoke: seed → login → create KB → upload → ingest ready → chat with citations across two users proving isolation
- [x] 8.2 Run `openspec validate add-rag-mvp` and fix any issues
- [x] 8.3 README: setup (compose swap, env, uv, seed, run backend + frontend)
