# document-ingestion Specification (delta)

## ADDED Requirements

### Requirement: Ingestion guarded by embedding configuration validation
The system SHALL verify that the configured embedding model and dimension match the database embedding registry before processing a document, and SHALL reject ingestion with an actionable error (naming both configurations and the `reembed` remedy) on mismatch, rather than failing on vector insert.

#### Scenario: Ingestion with matching configuration
- **WHEN** a document is uploaded while settings match the registry
- **THEN** ingestion proceeds normally

#### Scenario: Ingestion with mismatched configuration
- **WHEN** a document is uploaded while the configured embedding model or dimension differs from the registry
- **THEN** the request is rejected with a conflict error naming the configured and registered model/dimension and the `reembed` command
- **AND** no chunks are written

## MODIFIED Requirements

### Requirement: Parse, chunk, and embed
The system SHALL extract text from an uploaded document, split it into overlapping chunks, generate an embedding for each chunk via the configured embedding model, and store each chunk with its text, embedding vector, `kb_id`, source document reference, and positional metadata. The embedding column dimension SHALL be defined by the database schema and embedding registry rather than hardcoded in application code, and chunks written by ingestion SHALL always include an embedding.

#### Scenario: Text document produces embedded chunks
- **WHEN** a supported document is processed
- **THEN** its text is split into chunks
- **AND** each chunk is stored with an embedding vector and its `kb_id` and document reference

#### Scenario: Embedding dimension is consistent
- **WHEN** chunks are embedded
- **THEN** all stored vectors share the registered embedding model's fixed dimension so similarity search is valid
