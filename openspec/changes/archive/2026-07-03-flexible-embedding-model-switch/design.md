# Design: flexible-embedding-model-switch

## Context

The embedding model is configured in `.env` (`EMBEDDING_MODEL`, `EMBEDDING_DIM`) and read via `app/core/config.py`. The ORM binds `chunks.embedding` to `HALFVEC(settings.embedding_dim)` at import time (`app/models/__init__.py:150`), but the real column dimension is frozen in the initial Alembic migration (`b16bcf5b01b1`, `halfvec(3072)` with an HNSW `halfvec_cosine_ops` index). The database records nothing about which model produced the stored vectors. Result: editing `.env` to a model with a different dimension makes ingestion fail on insert with a raw pgvector dimension error, and stored vectors from the old model would be semantically incompatible even when dimensions happen to match.

This is a development-phase system: a single global embedding model, downtime/degraded search during a switch is acceptable, and raw uploaded files are not retained (re-chunking is handled by re-uploading).

## Goals / Non-Goals

**Goals:**
- The database knows which embedding model/dimension its vectors were built with (registry = "actual" state; settings = "desired" state).
- Mismatch is detected at startup and before ingestion, with an actionable error instead of an insert failure.
- One command (`python -m app.cli reembed`) migrates the live database to the configured model, re-embedding from stored chunk content, idempotently and resumably.
- Fresh installs work at any configured dimension without editing migrations.

**Non-Goals:**
- Per-KB or coexisting embedding models (registry is global one-row; schema leaves room to grow later).
- Zero-downtime / blue-green switching; search is degraded while `reembed` runs.
- Raw file retention or automatic re-chunking.
- Backfilling semantic compatibility checks beyond model-name + dimension equality.

## Decisions

### Decision: One-row `embedding_config` registry table
Columns: `id` (constant single-row key), `model` (text), `dim` (int), `updated_at`. Seeded by migration from settings at `alembic upgrade` time.
- *Why not settings-only?* Settings describe intent; only the DB can describe what the vectors actually are. Without the registry the mismatch is undetectable.
- *Alternative considered:* per-chunk or per-document `model` column — more flexible (enables Level-3 coexistence later) but adds per-row overhead and query complexity we don't need for a single global model. The one-row table can be extended to per-KB rows later without discarding this work.

### Decision: Validate at startup AND at ingestion entry
Startup check (FastAPI lifespan) fails the app with a message naming desired vs. actual and the remedy (`reembed`). The same check runs before each document ingestion, guarding against `.env` edits after the app started. Error surfaces as HTTP 409 with the same message.
- *Why both?* Startup-only misses live `.env`/restartless changes; ingestion-only lets a misconfigured app serve retrieval built on stale assumptions silently.

### Decision: `chunks.embedding` becomes nullable; NULL means "awaiting re-embed"
The `reembed` flow alters the column type with `USING NULL`, keeping chunk rows (ids, content, metadata) stable and avoiding delete/reinsert. Retrieval adds `WHERE embedding IS NOT NULL`. Ingestion still always writes an embedding, so NULL only occurs mid-switch.
- *Alternative considered:* truncate chunks and re-ingest — loses chunk ids/metadata and requires re-upload since raw files aren't kept.

### Decision: ORM column stops reading `settings.embedding_dim` at import time
The mapped column uses an unparameterized `HALFVEC` (dimension enforced by the DB schema, validated by the registry check). This removes the second, silently-drifting source of truth in Python.

### Decision: `reembed` orchestration order
1. Mark all documents `processing` (UI shows degraded state).
2. Drop HNSW index.
3. `ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(<new dim>) USING NULL` (skipped if dim unchanged — model-only switch just nulls embeddings).
4. Batch per document: select `content` of chunks `WHERE embedding IS NULL`, embed with new model, `UPDATE`; flip document to `ready` when its chunks are done.
5. Recreate HNSW index after all updates (bulk-load then index is far faster than incremental HNSW inserts).
6. Update registry row to the new model/dim.

Idempotent/resumable: a re-run skips `ready` documents and picks up chunks `WHERE embedding IS NULL`; registry updates last, so an interrupted run still reports mismatch and can be resumed. Steps 2–3 are conditional on current schema state so re-running after step 5 is harmless.

### Decision: Alembic stops hardcoding the dimension for fresh installs
New migration adds `embedding_config` and makes `embedding` nullable. Fresh-install dimension comes from settings at upgrade time (read inside the migration), and the registry row is seeded to match, so a new clone at `bge-m3/1024` boots cleanly.

## Risks / Trade-offs

- [Search degraded during reembed] → documents flip back to `ready` incrementally; retrieval filters `embedding IS NOT NULL`, returning partial results rather than erroring. Acceptable per requirements.
- [Interrupted reembed leaves mixed state] → registry is updated last; startup/ingestion checks keep failing until a re-run completes; NULL-embedding chunks make remaining work self-describing.
- [Same-dimension model swap is undetectable by pgvector] → registry compares model name too, not just dim, so e.g. two different 1024-dim models still trigger `reembed`.
- [Migration reading settings makes upgrades environment-dependent] → confined to the fresh-install path; existing databases keep their column dim and rely on `reembed` for changes.
- [Embedding API rate limits/failures mid-run] → batched calls with per-batch commit; failures leave NULLs and a resumable state, and the command reports which documents remain.

## Migration Plan

1. Apply new Alembic migration (adds registry seeded to the *current* DB state — `gemini/gemini-embedding-001`, 3072 — and makes `embedding` nullable). No data loss; app behaves as before if settings unchanged.
2. To switch models: edit `.env`, restart (app refuses to serve ingestion, message points to `reembed`), run `python -m app.cli reembed`, done.
3. Rollback: revert `.env` and run `reembed` again — the operation is symmetric.

## Open Questions

- Should the startup check hard-fail the whole app or only disable ingestion/retrieval routes? (Current choice: hard-fail — simplest and clearest for a dev-phase system.)
- Seeding the registry for the *existing* dev database: migration seeds from the live column's dimension via introspection where possible, falling back to settings — verify against the actual dev DB during implementation.
