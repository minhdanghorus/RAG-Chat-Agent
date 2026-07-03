# chat-retrieval Specification (delta)

## ADDED Requirements

### Requirement: Retrieval excludes chunks pending re-embedding
The retrieval tool SHALL consider only chunks that have an embedding vector, excluding chunks whose embedding is NULL (awaiting re-embedding), and SHALL return partial or empty results during a re-embedding window rather than erroring.

#### Scenario: Chunks without embeddings are skipped
- **WHEN** a similarity search runs while some chunks have NULL embeddings
- **THEN** only chunks with embeddings are candidates and the search completes without error

#### Scenario: Retrieval during a full re-embed
- **WHEN** a query arrives while all chunks in scope lack embeddings
- **THEN** the tool returns no chunks and the agent responds that it lacks grounding, per existing behavior
