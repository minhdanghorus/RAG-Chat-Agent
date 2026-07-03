## ADDED Requirements

### Requirement: Document deletion from a KB
The system SHALL allow a user with manage permission on a KB to delete a document from that KB. Deletion SHALL remove the document record and all of its chunks and embeddings, so the document immediately stops appearing in retrieval results. This enables replacing a file by deleting it and uploading a new version.

#### Scenario: Delete a document
- **WHEN** an authorized user deletes a document from a KB they can manage
- **THEN** the document, its chunks, and its embeddings are removed
- **AND** subsequent retrieval in that KB returns no passages from the deleted document

#### Scenario: Delete without manage permission
- **WHEN** a user attempts to delete a document in a KB they cannot manage
- **THEN** the system rejects the request as forbidden

#### Scenario: Document not in the given KB
- **WHEN** a delete targets a document id that does not belong to the KB in the request path
- **THEN** the system responds with not found and deletes nothing

#### Scenario: Re-upload after delete
- **WHEN** a user deletes a document and uploads a new file with the same filename
- **THEN** the new file is ingested as a fresh document and becomes retrievable once ready
