## 1. Streaming spike

- [x] 1.1 Verify token streaming end-to-end with the configured chat model: minimal script calling `graph.astream(stream_mode="messages")` and confirming incremental token events from the agent node (fallback plan per design if callbacks don't propagate) — spike found `astream` fails on the sync `PostgresSaver`; adopted the sync-`stream` worker-thread bridge (see design decision #4). Verified 6 incremental agent-node token events.

## 2. Data model & migration

- [x] 2.1 Add `Agent` model (owner, name, description, system_prompt, kb_ids, model_name, temperature, retrieval_top_k, retrieval_threshold) and `AgentAccess` model (agent_id, user_id, unique pair)
- [x] 2.2 Add nullable `agent_id` FK to `ChatSession` (keep `kb_ids` column in place, no longer read)
- [x] 2.3 Startup seed/backfill: per user owning sessions, create a "Default Assistant" agent (current hardcoded prompt, union of their sessions' kb_ids) and point their sessions' `agent_id` at it

## 3. Access control & agent services

- [x] 3.1 Extend `services/access.py`: `accessible_agents`, `can_use_agent` (owner or grant), `can_manage_agent` (owner only)
- [x] 3.2 Agent KB validation on create/edit: every kb_id must be readable by the owner (reuse `resolve_selected_kb_ids`), rejecting the whole write otherwise

## 4. Agent API

- [x] 4.1 `POST/GET/PATCH /agents` — create, list accessible, edit (owner only); model/retrieval settings default from global config
- [x] 4.2 `DELETE /agents/{id}` — owner only, 409 while sessions reference the agent
- [x] 4.3 Grant routes: list/add/remove `/agents/{id}/access` entries (owner only)
- [x] 4.4 Schemas for agent in/out and grants

## 5. Chat flow rewiring

- [x] 5.1 Session creation takes `agent_id` (validated via `can_use_agent`) instead of `kb_ids`; session list includes agent info
- [x] 5.2 Resolve session agent at message time; put system prompt, model settings, retrieval settings, and agent kb_ids into graph state (no intersection with the chatting user's KB access)
- [x] 5.3 `graph.py`: `_agent_node` builds system message and LLM from state; `_tools_node` passes top_k/threshold to `retrieve()`; `retrieval.py` accepts those params
- [x] 5.4 `llm.py`: parameterized `get_chat_llm(model, temperature, streaming)` with per-config caching, streaming enabled for chat

## 6. Real streaming endpoint

- [x] 6.1 Replace the worker-thread replay bridge in `chat.py` with `async for` over `graph.astream(stream_mode="messages")`, emitting `token` SSE events only for agent-node tokens
- [x] 6.2 Emit `citations` from final graph state and `done` after the stream; keep the SSE event protocol unchanged; surface errors as the existing `error` event

## 7. Document deletion

- [x] 7.1 `DELETE /kb/{kb_id}/documents/{doc_id}` guarded by `can_manage_kb`, 404 if the document is not in that KB (cascades remove chunks/embeddings)

## 8. Frontend

- [x] 8.1 Agents page: list accessible agents; create/edit form (name, description, instruction, KB multi-select from accessible KBs, model + retrieval settings); delete
- [x] 8.2 Access grants UI on the agent edit page (add/remove users), with copy noting granted users can search the agent's KBs through chat
- [x] 8.3 New-chat flow: pick an agent first (replace the KB picker); show the session's agent in the chat view
- [x] 8.4 Confirm incremental token rendering works against real streaming (adjust client SSE handling if needed)
- [x] 8.5 Delete button per document in the KB document list, with confirmation

## 9. Verification

- [x] 9.1 Backend tests: agent CRUD + grant permissions, KB attachment validation, session creation with agent, retrieval scoped to agent KBs (including a KB the chatting user cannot read), document delete permissions and cascade
- [~] 9.2 Manual end-to-end pass: create agent → grant a second user → second user chats and gets streamed, cited answers from a private KB → edit agent prompt and see it apply to the old session → delete and re-upload a document — substance verified by automated **live** tests (`test_granted_user_retrieves_from_private_kb`: grant + second-user streamed cited answer from a KB they cannot read; `test_document_delete_permission_and_cascade`: delete + cascade). Live-reference prompt edits are message-time-resolved (design #1/#5). Human browser click-through NOT performed — pending a manual UI pass.
