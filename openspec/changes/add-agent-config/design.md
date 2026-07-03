## Context

The MVP hardcodes the assistant: `SYSTEM_PROMPT` is a constant in `backend/app/agent/graph.py`, model/temperature come from global env config in `llm.py`, retrieval params are fixed in `retrieval.py`, and KB scope is chosen per session and stored in `ChatSession.kb_ids`. Streaming is simulated: `chat.py` runs the graph to completion on a worker thread, then replays the finished answer in 24-character SSE chunks. Documents can be uploaded but never deleted.

Authorization today is ownership-based only (personal or team ownership of KBs, via `services/access.py`). There is no admin role. The `add-rag-mvp` change is complete but not yet archived, so the baseline specs live in `openspec/changes/add-rag-mvp/specs/`.

## Goals / Non-Goals

**Goals:**
- First-class Agent entity carrying instruction, KB scope, model settings, and retrieval settings.
- Creator-managed per-user access grants, where agent access implies retrieval access to the agent's KBs.
- Agent-first chat flow with sessions holding a live reference to their agent.
- Genuine token-level streaming from the LLM to the client.
- Document deletion so users can replace files with new versions.

**Non-Goals:**
- Admin roles or org-wide agent governance (creator-managed only).
- Agent versioning / session snapshots of agent config (live reference is chosen deliberately).
- Automatic replace-on-reupload of same-filename documents (manual delete-then-reupload).
- Team-owned agents (agents are owned by individual users; sharing is per-user grants).
- Public/unauthenticated agents.

## Decisions

### 1. Agent as a row, sessions hold a live reference
`agents` table: `id`, `owner_user_id`, `name`, `description`, `system_prompt`, `kb_ids uuid[]`, `model_name`, `temperature`, `retrieval_top_k`, `retrieval_threshold`, timestamps. `chat_sessions` gains `agent_id` (FK, RESTRICT on delete while sessions exist — or nullable with fallback; see Migration). Sessions resolve the agent at message time, so edits to prompt/KBs/settings apply to all future messages in existing sessions.

*Alternative considered:* snapshotting agent config into the session at creation. Rejected: more storage and drift complexity, and live-updating shared agents is the expected behavior ("fix the prompt once, everyone benefits").

### 2. Access = ownership or explicit grant; grants confer KB retrieval access
New `agent_access` table (`agent_id`, `user_id`, unique pair). `services/access.py` gains `accessible_agents(db, user)` (owned + granted), `can_use_agent`, `can_manage_agent` (owner only). Retrieval scope for a session is **the agent's `kb_ids` as stored** — no intersection with the chatting user's KB access. This is the point of the feature: an HR bot can answer from docs the user cannot open. Users still cannot list/download those KBs' documents; only retrieval passages flow through chat.

**Write-time invariant:** on agent create/edit, every KB in `kb_ids` must be readable by the *owner* (`resolve_selected_kb_ids` reuse). Validated on every write, not just creation, so an owner can never attach a KB they merely guessed the ID of.

*Alternative considered:* intersecting agent KBs with the chatting user's access at retrieval time (current session behavior). Rejected per product decision: shared agents would silently answer from nothing for users without direct KB access.

### 3. Trust stored kb_ids at retrieval time
Retrieval reads the agent's `kb_ids` without re-checking the owner's current access on every message (cheap, predictable). If an owner later loses access to a KB (e.g. leaves a team), the agent keeps searching it until the next edit re-validates. Accepted as a trade-off; see Risks.

### 4. Real streaming via `stream_mode="messages"` (sync stream on a worker thread)
`chat.py`'s message endpoint forwards only tokens whose `metadata["langgraph_node"] == "agent"` as SSE `token` events (tool-call deltas and ToolMessages are not forwarded). After the stream ends, read final state for `citations` and emit the existing `citations` + `done` events — the SSE event protocol is unchanged, so the frontend change is limited to rendering tokens as they arrive (which it already does). `get_chat_llm` constructs the client with streaming enabled.

**Spike outcome (task 1.1):** `graph.astream(...)` raises `NotImplementedError` because the graph's checkpointer is the sync `PostgresSaver` (no async methods), and `get_history` also depends on the sync `get_state`. The fallback from Risks was taken: run the **sync** `graph.stream(inputs, config, stream_mode="messages")` on a worker thread and bridge genuine tokens to the async SSE response through an `asyncio.Queue`. This still emits tokens *while the model generates* (verified: 6 incremental token events for a one-line reply) — the key difference from the old run-to-completion replay bridge — while keeping the checkpointer and `get_history` sync.

*Alternative considered:* switching to `AsyncPostgresSaver` and making all chat routes async. Rejected for this iteration: larger blast radius (every `get_state` call and checkpointer init becomes async) for no additional user-visible benefit.

### 5. Per-agent LLM and retrieval parameters flow through graph state
`ChatState` gains the resolved agent config (system prompt, model, temperature, top_k, threshold), populated by `chat.py` from the session's agent before invoking. `_agent_node` builds the system message and LLM from state instead of module constants; `_tools_node` passes top_k/threshold into `retrieve()`. `get_chat_llm` becomes parameterized (cache keyed by model+temperature+streaming). Env config remains the source of defaults for new agents.

### 6. Migration: seed "Default Assistant", backfill sessions
Startup migration (consistent with the MVP's `create_all` approach): create new tables/column, insert a "Default Assistant" agent per... **no** — a single system-wide seeding won't fit creator-ownership. Instead: for each user who owns at least one chat session, seed one "Default Assistant" agent owned by that user with the current hardcoded prompt and the union of that user's session `kb_ids`; backfill their sessions' `agent_id` to it. `ChatSession.kb_ids` stays in place but is no longer read (dropped in a later cleanup), so rollback is trivial.

### 7. Document deletion is a plain row delete
`DELETE /kb/{kb_id}/documents/{doc_id}` guarded by `can_manage_kb`; 404 if the document doesn't belong to that KB. ORM/DB cascades (`Document.chunks`, `ondelete="CASCADE"`) already remove chunks and embeddings, so retrieval stops seeing the document immediately. No soft delete, no original-file storage to clean.

## Risks / Trade-offs

- [Agent grants leak KB content by design] → The write-time invariant limits exposure to KBs the *owner* legitimately reads; document listing/download endpoints still enforce direct KB access; make the implication visible in the grant UI copy ("users you grant can search these KBs through this agent").
- [Owner loses KB access after attaching it] → Stored `kb_ids` keep working until the next edit. Mitigation: re-validate on every edit; acceptable residual risk for this iteration (no background sweeps).
- [Live reference surprises: editing an agent changes old sessions' behavior] → Chosen deliberately; UI should show which agent a session uses.
- [Streaming with sync graph nodes] → `stream_mode="messages"` requires LLM callbacks to propagate; verify with the Green Node/OpenAI-compatible client that token events actually stream (spike early in implementation). Fallback: async node variants.
- [Agent deletion with live sessions] → Restrict delete while sessions reference the agent, or nullify + fall back to an error prompting re-selection; decide in implementation (restrict is simplest and chosen by default).
- [Per-user seeded default agents multiply rows] → Bounded by user count; acceptable.

## Migration Plan

1. Deploy schema additions (`agents`, `agent_access`, `chat_sessions.agent_id` nullable).
2. Run seed/backfill (per-owner Default Assistant, sessions pointed at it).
3. Ship API + frontend; session creation now requires `agent_id`.
4. `ChatSession.kb_ids` left unread; drop in a later cleanup change.

Rollback: previous code ignores `agent_id` and still reads `kb_ids`, which is untouched.

## Open Questions

- None blocking. Streaming behavior of the Green Node chat endpoint should be verified in the first implementation task (spike).
