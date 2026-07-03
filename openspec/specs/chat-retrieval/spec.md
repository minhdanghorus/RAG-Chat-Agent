# chat-retrieval Specification

## Purpose
TBD - created by archiving change add-rag-mvp. Update Purpose after archive.
## Requirements
### Requirement: KB selection per chat
The system SHALL let a user start a chat session scoped to one or more KBs chosen from their resolved access set. The selected KBs SHALL define the retrieval scope for that session.

#### Scenario: Start chat with allowed KBs
- **WHEN** a user starts a chat and selects KBs they can access
- **THEN** the session is created bound to those `kb_id` values

#### Scenario: Selecting an inaccessible KB is rejected
- **WHEN** a user attempts to include a KB outside their access set
- **THEN** the system rejects the selection as forbidden

### Requirement: Isolation-enforced retrieval tool
The agent SHALL retrieve context through a `retrieve_kb` tool that performs vector similarity search constrained to the intersection of the session's selected KBs and the caller's resolved access set. The tool SHALL never return chunks outside that constrained set, regardless of the model's tool arguments.

#### Scenario: Retrieval is scoped to the session KBs
- **WHEN** the agent calls `retrieve_kb` during a session
- **THEN** the similarity search filters candidates to the session's selected `kb_id` set

#### Scenario: Retrieval cannot be widened by tool arguments
- **WHEN** the model requests retrieval targeting a `kb_id` not in the caller's access set
- **THEN** the tool ignores that target and returns only permitted chunks

### Requirement: Grounded answers with citations
The system SHALL generate answers grounded in retrieved chunks and SHALL return citations identifying the source chunks/documents used, so the user can trace an answer to its source.

#### Scenario: Answer includes citations
- **WHEN** the agent produces an answer using retrieved chunks
- **THEN** the response includes references to the source document(s) and chunk(s) used

#### Scenario: No relevant context
- **WHEN** retrieval returns no relevant chunks for the query
- **THEN** the agent responds that it lacks grounding rather than fabricating an answer

### Requirement: Streaming responses
The system SHALL stream the assistant's answer to the client incrementally (token/segment level) so replies render progressively.

#### Scenario: Tokens stream to the client
- **WHEN** the agent generates an answer
- **THEN** the client receives incremental output before the full answer is complete

### Requirement: Persisted conversation history
The system SHALL persist conversation history per session in Postgres via a LangGraph checkpointer, so a session's prior turns are available on reload and inform later turns.

#### Scenario: History survives reload
- **WHEN** a user reopens an existing session
- **THEN** the prior turns of that session are retrievable

#### Scenario: History is scoped to its owner
- **WHEN** a user requests a session
- **THEN** only sessions belonging to that user are returned

### Requirement: Retrieval excludes chunks pending re-embedding
The retrieval tool SHALL consider only chunks that have an embedding vector, excluding chunks whose embedding is NULL (awaiting re-embedding), and SHALL return partial or empty results during a re-embedding window rather than erroring.

#### Scenario: Chunks without embeddings are skipped
- **WHEN** a similarity search runs while some chunks have NULL embeddings
- **THEN** only chunks with embeddings are candidates and the search completes without error

#### Scenario: Retrieval during a full re-embed
- **WHEN** a query arrives while all chunks in scope lack embeddings
- **THEN** the tool returns no chunks and the agent responds that it lacks grounding, per existing behavior

