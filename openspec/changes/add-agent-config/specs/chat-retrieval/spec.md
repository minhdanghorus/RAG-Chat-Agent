## MODIFIED Requirements

### Requirement: KB selection per chat
The system SHALL let a user start a chat session by selecting one agent from the set of agents they can use (owned or granted). The session SHALL store a live reference to the agent; the agent's KB set, system prompt, model settings, and retrieval settings SHALL define the session's behavior, resolved at message time so agent edits apply to future messages in existing sessions. Sessions SHALL no longer carry their own KB selection.

#### Scenario: Start chat with an accessible agent
- **WHEN** a user starts a chat and selects an agent they own or are granted
- **THEN** the session is created bound to that agent's id

#### Scenario: Selecting an inaccessible agent is rejected
- **WHEN** a user attempts to start a session with an agent they neither own nor are granted
- **THEN** the system rejects the selection as forbidden

#### Scenario: Agent edits apply to existing sessions
- **WHEN** an agent's prompt or KB set is edited after a session was created with it
- **THEN** subsequent messages in that session use the updated configuration

### Requirement: Isolation-enforced retrieval tool
The agent SHALL retrieve context through a `retrieve_kb` tool that performs vector similarity search constrained to the session agent's stored KB set, using the agent's retrieval settings (top_k, similarity threshold). The tool SHALL never return chunks outside that set, regardless of the model's tool arguments.

#### Scenario: Retrieval is scoped to the agent's KBs
- **WHEN** the model calls `retrieve_kb` during a session
- **THEN** the similarity search filters candidates to the session agent's `kb_id` set

#### Scenario: Retrieval cannot be widened by tool arguments
- **WHEN** the model requests retrieval targeting a `kb_id` not in the agent's KB set
- **THEN** the tool ignores that target and returns only permitted chunks

### Requirement: Streaming responses
The system SHALL stream the assistant's answer to the client as genuine incremental LLM output: token events SHALL be emitted while the model is still generating, not replayed after generation completes. Only assistant-visible answer tokens SHALL be streamed (tool-call activity is not forwarded as answer text), and citations SHALL be delivered when the answer completes.

#### Scenario: Tokens stream during generation
- **WHEN** the agent generates an answer
- **THEN** the client receives the first token events before the model has finished generating the full answer

#### Scenario: Tool activity is not leaked as answer text
- **WHEN** the model emits tool calls or the tool returns passages during a turn
- **THEN** the client's answer text contains only the assistant's final-answer tokens

#### Scenario: Citations follow the streamed answer
- **WHEN** the streamed answer completes
- **THEN** the client receives the citations for the retrieved sources used
