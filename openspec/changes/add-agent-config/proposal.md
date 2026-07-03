## Why

The chat experience is hardwired to a single built-in assistant: the system prompt is a constant in code, KB scope is picked ad hoc per session, and answers appear all at once because the backend fakes streaming (it runs the graph to completion, then replays the text in chunks). Users need to define purpose-built agents — own instruction, own knowledge scope, own model/retrieval tuning — share them with specific users, and see responses stream token-by-token. Separately, documents cannot be deleted, so there is no way to replace a file with a newer version.

## What Changes

- New **Agent** entity: name, description, system prompt, KB set, model settings (model name, temperature), retrieval settings (top_k, similarity threshold), owned by its creator.
- New **agent access grants**: the creator grants/revokes access per user. Access to an agent implies retrieval access to all of the agent's KBs, even KBs the user cannot browse directly (the agent is the product; raw documents stay hidden).
- Security invariant: an agent creator may only attach KBs they can read themselves — validated on every create/edit, so an agent can never republish a KB its creator does not have.
- **BREAKING** New-chat flow: users pick an agent first; `ChatSession` stores a live `agent_id` reference (agent edits affect future messages in existing sessions). The per-session KB picker and `ChatSession.kb_ids`-based scoping are removed from the flow. Existing sessions migrate to a seeded "Default Assistant" agent built from the current hardcoded prompt.
- **Real token streaming**: replace the run-to-completion-then-replay bridge with `graph.astream(stream_mode="messages")`, emitting genuine LLM tokens as SSE events (agent-node tokens only), citations at the end. The LLM is invoked in streaming mode.
- **Document deletion**: `DELETE /kb/{kb_id}/documents/{doc_id}` guarded by `can_manage_kb`, plus a delete button in the frontend document list. Existing DB cascades remove chunks/embeddings. Re-uploading the same filename without deleting first simply creates a duplicate (manual delete-then-reupload flow).

## Capabilities

### New Capabilities
- `agent-management`: creating, editing, deleting agents (prompt, KBs, model/retrieval settings) and managing per-user access grants; the access rules that follow from grants.

### Modified Capabilities
- `chat-retrieval`: sessions are created from an agent instead of a KB list; retrieval scope, system prompt, and model/retrieval parameters come from the session's agent (live reference); responses stream real LLM tokens instead of replayed chunks.
- `document-ingestion`: documents can be deleted from a KB, removing their chunks/embeddings from retrieval, enabling re-upload of new versions.

## Impact

- **Backend models**: new `agents` and `agent_access` tables; `chat_sessions.agent_id` column (live FK); migration seeding a "Default Assistant" agent for existing sessions.
- **Backend services**: `services/access.py` gains agent access helpers; retrieval scope resolution changes from session `kb_ids` to agent KBs.
- **Backend agent graph**: `graph.py` system prompt, model settings, and retrieval params become per-invocation state resolved from the session's agent; `llm.py` supports streaming and per-agent model/temperature.
- **Backend API**: new `/agents` CRUD + grants routes; `chat.py` session creation takes `agent_id`, message endpoint switches to `astream`; `documents.py` gains DELETE.
- **Frontend**: new agent config pages (list/create/edit, KB multi-select, access grants); new-chat flow starts with agent selection; KB picker removed; chat view renders incremental tokens; document list gains delete.
