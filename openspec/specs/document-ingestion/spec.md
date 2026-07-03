# document-ingestion Specification

## Purpose
TBD - created by archiving change add-rag-mvp. Update Purpose after archive.
## Requirements
### Requirement: Document upload into a KB
The system SHALL allow a user with manage permission on a KB to upload a document (PDF, DOCX, or TXT) into that KB. The system SHALL record the document with its filename, KB reference, and an ingestion status.

#### Scenario: Upload a supported document
- **WHEN** an authorized user uploads a PDF/DOCX/TXT file to a KB they can manage
- **THEN** a document record is created with status "pending" and associated with that KB

#### Scenario: Unsupported file type rejected
- **WHEN** a user uploads a file whose type is not PDF/DOCX/TXT
- **THEN** the system rejects the upload and creates no document record

#### Scenario: Upload without manage permission
- **WHEN** a user uploads to a KB they cannot manage
- **THEN** the system rejects the request as forbidden

### Requirement: Parse, chunk, and embed
The system SHALL extract text from an uploaded document, split it into overlapping chunks, generate an embedding for each chunk via the Green Node embedding model, and store each chunk with its text, embedding vector, `kb_id`, source document reference, and positional metadata.

#### Scenario: Text document produces embedded chunks
- **WHEN** a supported document is processed
- **THEN** its text is split into chunks
- **AND** each chunk is stored with an embedding vector and its `kb_id` and document reference

#### Scenario: Embedding dimension is consistent
- **WHEN** chunks are embedded
- **THEN** all stored vectors share the embedding model's fixed dimension so similarity search is valid

### Requirement: Ingestion status tracking
The system SHALL update a document's status to reflect ingestion progress ("pending" → "processing" → "ready", or "failed" on error) so the frontend can show whether a document is searchable.

#### Scenario: Successful ingestion marks document ready
- **WHEN** all chunks of a document are embedded and stored
- **THEN** the document status is set to "ready"

#### Scenario: Failed ingestion is surfaced
- **WHEN** parsing or embedding fails for a document
- **THEN** the document status is set to "failed" and the error is recorded

