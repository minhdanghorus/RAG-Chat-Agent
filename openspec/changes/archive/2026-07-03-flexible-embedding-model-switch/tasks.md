# Tasks: flexible-embedding-model-switch

## 1. Schema & registry

- [x] 1.1 Add `EmbeddingConfig` model (single-row table: `model`, `dim`, `updated_at`) in `app/models/__init__.py`
- [x] 1.2 Change `Chunk.embedding` to nullable, unparameterized `HALFVEC` (drop the import-time `settings.embedding_dim` binding)
- [x] 1.3 Alembic migration: create `embedding_config`, seed it from the live `chunks.embedding` column dimension (introspection; fall back to settings on fresh DB) with the current settings model name, and make `chunks.embedding` nullable
- [x] 1.4 Verify migration on the existing dev database (registry row = gemini/gemini-embedding-001, 3072) and on a fresh database with bge-m3/1024

## 2. Mismatch validation

- [x] 2.1 Add a registry service (`get_active_config`, `check_settings_match`) returning a structured mismatch describing desired vs. actual and the `reembed` remedy
- [x] 2.2 Startup check in FastAPI lifespan: fail app start on mismatch with the actionable message
- [x] 2.3 Ingestion guard: reject document processing with HTTP 409 (same message) on mismatch, before any chunks are written
- [x] 2.4 Tests: startup pass/fail, ingestion 409 on mismatch (including same-dim different-model case)

## 3. Retrieval null-safety

- [x] 3.1 Add `embedding IS NOT NULL` filter to the similarity search in the retrieval service
- [x] 3.2 Test: retrieval skips NULL-embedding chunks and returns empty (no error) when all in-scope chunks are NULL

## 4. Reembed command

- [x] 4.1 CLI entry point `python -m app.cli reembed` (argparse or typer; no-op exit when settings match registry and no NULL embeddings)
- [x] 4.2 Schema phase: mark all documents `processing`, drop HNSW index, `ALTER COLUMN embedding TYPE halfvec(<dim>) USING NULL` — each step conditional on current state so re-runs are safe
- [x] 4.3 Backfill phase: per document, batch-embed chunks `WHERE embedding IS NULL` from `content` with per-batch commit; flip document to `ready` when complete; skip already-`ready` documents
- [x] 4.4 Finalize phase: recreate HNSW index (`halfvec_cosine_ops`), then update registry row to the configured model/dim
- [x] 4.5 Failure handling: report remaining documents/chunks on error, exit nonzero, leave state resumable
- [x] 4.6 Tests: full switch (dim change), model-only switch (same dim), resume after simulated interruption, registry updated only at completion

## 5. Docs & config

- [x] 5.1 Update `.env.example` comments: changing model/dim requires `reembed`
- [x] 5.2 Update README: embedding-model switch procedure and degraded-search window
