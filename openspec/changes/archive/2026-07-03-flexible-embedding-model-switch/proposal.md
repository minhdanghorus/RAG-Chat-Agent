# Proposal: flexible-embedding-model-switch

## Why

Changing `EMBEDDING_MODEL`/`EMBEDDING_DIM` in `.env` silently breaks ingestion: the app generates vectors of the new dimension while the `chunks.embedding` column and its HNSW index remain fixed at the old dimension (currently `halfvec(3072)`), so inserts fail with a cryptic pgvector error. Nothing in the database records which model produced the stored vectors, so the mismatch cannot even be detected — only tripped over. During development we want to experiment with embedding models freely, with a clear, guided path to switch.

## What Changes

- Add a one-row `embedding_config` registry table in Postgres recording the active embedding model and dimension (the "actual" state, vs. the "desired" state in settings).
- Validate desired-vs-actual at app startup and before each document ingestion; on mismatch, fail fast with an actionable error naming both configurations and the remedy command, instead of failing on insert.
- Add an idempotent, batched `reembed` CLI command that switches the live database to the configured model: drop the HNSW index, alter the embedding column to the new dimension (clearing old vectors), re-embed every chunk from its stored `content`, rebuild the index, and update the registry. Interrupted runs can be re-invoked and resume from unembedded chunks.
- **BREAKING**: `chunks.embedding` becomes nullable (NULL = awaiting re-embed); retrieval filters `embedding IS NOT NULL`. Alembic migrations stop hardcoding the dimension; fresh installs derive it from settings and seed the registry row.

Out of scope: per-KB embedding models, coexisting models, raw-file retention / re-chunking (a chunking change is handled by re-uploading documents).

## Capabilities

### New Capabilities
- `embedding-config`: Tracking the active embedding model/dimension in the database, validating it against application settings (startup + ingestion), and the `reembed` orchestration that migrates stored vectors to a new model.

### Modified Capabilities
- `document-ingestion`: Ingestion SHALL refuse to process documents while the configured embedding model/dimension disagrees with the database registry, surfacing the mismatch instead of failing on insert.
- `chat-retrieval`: Similarity search SHALL consider only chunks that have an embedding (excluding chunks pending re-embed), and SHALL degrade gracefully rather than error during a re-embed window.

## Impact

- **Schema**: new `embedding_config` table; `chunks.embedding` nullable; new Alembic migration; existing initial migration's hardcoded `3072` superseded for fresh installs.
- **Backend code**: `app/core/config.py` (no change to fields, becomes "desired" side), `app/models/__init__.py` (ORM column no longer bound to `settings.embedding_dim` at import time), `app/services/embeddings.py`, ingestion service, retrieval query, app startup lifecycle, new CLI entry point (`python -m app.cli reembed`).
- **Ops**: switching models is now `edit .env → run reembed`; search is degraded (fewer/no results) while re-embedding runs, acceptable for development use.
- **Docs**: README embedding-model section and `.env.example` comments.
