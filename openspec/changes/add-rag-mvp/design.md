## Context

Greenfield project (`D:\RAG-Chat-Agent`), currently a bare `uv` Python project. The team has substantial LangGraph experience (checkpointing, tool-calling, hierarchical/multi-agent, LangSmith, and multimodal ID extraction) in a sibling repo `D:\langchain\LangChain`, and already wires the Green Node LLM gateway via `ChatOpenAI(base_url, api_key, model)` with `LLM_*` env vars. An existing Docker Compose stack (`D:\postgres_sql\compose.yml`) runs Postgres 18, pgAdmin, and redis-stack.

The product goal is an MVP RAG platform where users upload documents and chat about them, with per-user and per-team isolation, built so it can later become a tool/MCP-using agent without a rewrite.

Constraints:
- LLM and embeddings come from Green Node (OpenAI-compatible SDK, `api_key`).
- Postgres runs in Docker (host port 5433); app processes run locally.
- Data must be isolated by user and by team/department; the agent is configured with which KB(s) it may search.

## Goals / Non-Goals

**Goals:**
- Working RAG loop: upload → ingest → chat with grounded, cited, streamed answers.
- Hard isolation by `kb_id`, enforced at both an authorization gate and the retrieval query.
- Agent-shaped chat loop (retrieval as a tool) so future tools/MCP are additive.
- Persisted conversation history using a Postgres checkpointer.
- One data store (Postgres + pgvector) for RBAC, vectors, and checkpoints.

**Non-Goals (deferred, additive later):**
- Multimodal / scanned-document ingestion (OCR, page-as-image embeddings).
- Admin-defined agents pre-bound to KBs; self-signup and SSO/OIDC.
- Full RBAC grant matrix (arbitrary per-KB user/team grants beyond owner/member).
- Hybrid/re-ranked search, multi-tool agents, MCP integration.

## Decisions

### Decision: PGVector (Postgres) over Qdrant for the vector store
An agent platform needs relational data anyway — users, teams, memberships, KBs, documents, sessions. Keeping vectors in the same Postgres gives transactional consistency between a document row and its chunks, lets isolation be a plain `WHERE kb_id = ANY(:allowed)` joined against permissions, and removes a second system to run/sync.
- **Alternative — Qdrant**: superior filtering and scale, but splits truth across two stores and still requires a relational DB. Revisit only if scale/filtering outgrows pgvector.
- **Mitigation for lock-in**: retrieval sits behind a thin `VectorStore` interface so a later swap to Qdrant is contained.

### Decision: `pgvector/pgvector:pg18` image (in-place swap)
The existing `postgres:18.0` image lacks the extension (`CREATE EXTENSION vector` → "extension not available", confirmed). `pgvector/pgvector:pg18` is the same Postgres 18 major with the extension bundled, so the existing `vng_db_volume` is reused with no dump/restore. One `CREATE EXTENSION vector;` is run once.
- **Alternative**: install pgvector into the running container — not persistent across container recreation. Rejected.
- **Watch**: the volume mounts `/var/lib/postgresql` (parent, not `/data`); verify tables persist after the swap.

### Decision: LangGraph agent with retrieval-as-tool (not a fixed RAG chain)
The chat loop is a minimal `StateGraph`: `agent (LLM) → [retrieve_kb tool] → agent → END`. Retrieval is the first tool. This matches the team's existing tool-calling pattern and makes MCP/other tools additive nodes rather than a rewrite — realizing the "agent, not chatbot" intent cheaply.
- **Alternative**: straight retrieve→stuff→generate chain. Simpler now, but boxes in the future agent direction. Rejected.

### Decision: Two-gate isolation
1. **Authorization gate (relational)**: on session create and each request, resolve the caller's accessible `kb_id` set (personal KBs ∪ team KBs). The session may only bind KBs from this set.
2. **Retrieval gate (query)**: `retrieve_kb` always filters to `session_kbs ∩ caller_access_set`, independent of what the model passes as tool arguments.
Defense-in-depth: a bug in one layer cannot leak another tenant's chunks.

### Decision: JWT identity now, seeded users (no self-signup yet)
Passwords are hashed (passlib) and identity travels as a signed JWT (python-jose) from day one, so self-signup/SSO is an additive endpoint later. Users/teams are seeded via a script/admin path for the MVP.

### Decision: Persistence via LangGraph Postgres checkpointer
Conversation history rides on `langgraph-checkpoint-postgres` against the same DB, so persisted history is near-free and consistent with app data. Session→user ownership is enforced relationally.

### Decision: Green Node via LangChain OpenAI wrappers
Reuse the established pattern: `ChatOpenAI` and `OpenAIEmbeddings` pointed at `LLM_BASE_URL`/`LLM_API_KEY`, model names from env. Chat model: `google/gemma-4-31b-it` (multimodal). Embedding model: `gemini/gemini-embedding-001`, **3072 dimensions**.

### Decision: Store embeddings as `halfvec(3072)` with an HNSW index
The embedding model outputs 3072 dims, above pgvector's 2000-dim limit for ANN indexes on the standard `vector` type. Storing as `halfvec(3072)` (half-precision) allows an HNSW index (halfvec supports up to 4000 dims), preserving the model's full representational quality with roughly half the storage and negligible precision loss. Requires pgvector ≥0.7, satisfied by the `pgvector/pgvector:pg18` image (0.8+).
- **Alternative — reduce to 1536 dims** via the model's Matryoshka output and use `vector(1536)`: simpler, ~half cost, small quality drop. Rejected to retain full quality.
- **Alternative — plain `vector(3072)` with no index (exact scan)**: acceptable at tiny scale but degrades as the corpus grows. Rejected as the primary store.
- Index: `USING hnsw (embedding halfvec_cosine_ops)`; queries cast the query vector to `halfvec` and order by cosine distance.

### Decision: Next.js/React frontend, FastAPI as the real API
User is comfortable with React and the destination is a rich agent UX (streaming, citations, tool traces). FastAPI stays the source of truth; the frontend consumes it (SSE for streaming), keeping the frontend swappable.

## Risks / Trade-offs

- **pgvector image swap corrupts/loses data** → Back up `vng_db_volume` (or `pg_dump`) before swapping; verify `\dt` after; major version unchanged (18) minimizes risk.
- **Embedding dimension mismatch** → Pin the embedding model and its dimension in config and the `vector(n)` column; validate at startup; re-embedding required if the model changes.
- **Isolation bug leaks tenant data** → Two-gate design; centralize the access-set resolver and the retrieval filter in one place each; add tests per the spec scenarios.
- **pgvector scale ceiling** → Acceptable for MVP (low millions); `VectorStore` interface keeps a Qdrant migration contained.
- **Green Node rate limits / latency** → Batch embeddings during ingestion; stream chat; handle failures by marking documents "failed" and surfacing errors.
- **Large-file ingestion blocks requests** → Ingest asynchronously (background task) with status polling; upload returns immediately as "pending".
- **JWT secret / API key leakage** → Load from `.env` (git-ignored); never log secrets.

## Migration Plan

1. Back up `vng_db_volume` (or `pg_dump` the `postgres` DB).
2. Edit `D:\postgres_sql\compose.yml`: `vng_db.image` → `pgvector/pgvector:pg18`; `docker compose up -d vng_db`.
3. Run `CREATE EXTENSION IF NOT EXISTS vector;`; verify existing tables with `\dt`.
4. Create app schema/migrations (users, teams, memberships, knowledge_bases, documents, chunks, sessions) + checkpointer tables.
5. Build backend (auth → KB → ingestion → chat), then frontend.
6. Rollback: revert the compose image to `postgres:18.0` and restore the volume backup; app schema is additive and can be dropped independently.

## Open Questions

- Chunking parameters (size / overlap) — start with a sensible default (e.g., ~800 tokens / ~100 overlap) and tune.
- Whether to reconcile `.python-version` (3.12.3) with `requires-python >=3.12` now or leave as-is.

_Resolved:_ embedding model `gemini/gemini-embedding-001` (3072 dims, stored as `halfvec(3072)` + HNSW); chat model `google/gemma-4-31b-it`.
