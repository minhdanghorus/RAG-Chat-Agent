# embedding-config Specification

## Purpose
Track the active embedding model and dimension in the database so it self-describes which model produced its stored vectors, validate that against application settings, and provide the orchestration that migrates stored vectors when the configured model changes.

## Requirements
### Requirement: Embedding configuration registry
The system SHALL persist the active embedding model name and vector dimension in the database (a single global registry record) so the database self-describes which model produced its stored vectors. Fresh installations SHALL seed the registry from application settings during schema migration.

#### Scenario: Registry seeded on fresh install
- **WHEN** migrations run against an empty database with `EMBEDDING_MODEL`/`EMBEDDING_DIM` configured
- **THEN** the embedding column is created with the configured dimension
- **AND** the registry records that model and dimension

#### Scenario: Registry reflects the stored vectors, not the settings
- **WHEN** application settings are changed to a different embedding model without migrating data
- **THEN** the registry still reports the model and dimension the stored vectors were built with

### Requirement: Fail-fast configuration mismatch validation
The system SHALL compare the configured embedding model and dimension against the registry at application startup and refuse to start on mismatch, reporting both configurations and the remedy command. Model name and dimension SHALL both be compared, so switching between different models of equal dimension is also detected.

#### Scenario: Startup with matching configuration
- **WHEN** the app starts and settings match the registry
- **THEN** the app starts normally

#### Scenario: Startup with mismatched configuration
- **WHEN** the app starts and the settings model or dimension differs from the registry
- **THEN** startup fails with an error naming the configured model/dim, the registry model/dim, and the `reembed` command

#### Scenario: Same-dimension model swap is detected
- **WHEN** settings name a different model whose dimension equals the registry dimension
- **THEN** the mismatch is still reported

### Requirement: Re-embedding orchestration command
The system SHALL provide a `reembed` CLI command that migrates stored vectors to the configured embedding model: it SHALL adjust the embedding column dimension if needed, clear old vectors, re-generate embeddings from stored chunk content in batches, rebuild the vector index after all embeddings are written, and update the registry only after completion.

#### Scenario: Successful model switch
- **WHEN** `reembed` runs with settings differing from the registry
- **THEN** every chunk's embedding is regenerated with the configured model from its stored content
- **AND** the vector index is rebuilt for the new dimension
- **AND** the registry is updated to the configured model and dimension

#### Scenario: No-op when already matching
- **WHEN** `reembed` runs while settings match the registry and no chunk lacks an embedding
- **THEN** the command exits successfully without modifying data

### Requirement: Resumable and idempotent re-embedding
The `reembed` command SHALL be safe to re-run after interruption: chunks pending re-embedding SHALL be identifiable (NULL embedding), completed documents SHALL be skipped, and the registry SHALL remain at the old configuration until the run completes so mismatch validation continues to signal unfinished work.

#### Scenario: Interrupted run resumes
- **WHEN** `reembed` is interrupted partway and invoked again
- **THEN** it re-embeds only chunks still lacking an embedding and completes the remaining documents

#### Scenario: Interrupted run keeps failing fast
- **WHEN** the app starts after an interrupted `reembed`
- **THEN** the mismatch error is still raised because the registry was not yet updated
