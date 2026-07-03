## ADDED Requirements

### Requirement: Agent creation and configuration
The system SHALL allow an authenticated user to create agents and edit agents they own. An agent SHALL carry: a name, an optional description, a system prompt (instruction), a set of KB ids defining its retrieval scope, model settings (model name, temperature), and retrieval settings (top_k, similarity threshold). Model and retrieval settings SHALL default from global configuration when not provided.

#### Scenario: Create an agent
- **WHEN** a user creates an agent with a name, system prompt, and a set of KBs they can read
- **THEN** the agent is stored with the user as owner and is immediately usable for new chat sessions

#### Scenario: Edit an agent
- **WHEN** the owner updates an agent's prompt, KB set, model settings, or retrieval settings
- **THEN** the changes are persisted and apply to all future messages in sessions using that agent

#### Scenario: Non-owner cannot edit
- **WHEN** a user who is not the owner attempts to edit or delete an agent
- **THEN** the system rejects the request as forbidden

### Requirement: Agent KB attachment restricted to owner-readable KBs
The system SHALL validate on every agent create and edit that each KB in the agent's KB set is readable by the agent's owner, and SHALL reject the write otherwise. This prevents an agent from republishing a KB its owner cannot read.

#### Scenario: Attaching an inaccessible KB is rejected
- **WHEN** an owner creates or edits an agent to include a KB id outside their resolved access set
- **THEN** the system rejects the request as forbidden and persists no changes

#### Scenario: Re-validation on edit
- **WHEN** an owner edits any field of an agent
- **THEN** the system re-validates the entire KB set against the owner's current access

### Requirement: Per-user agent access grants
The system SHALL allow an agent's owner to grant and revoke access to the agent for individual users. A user SHALL be able to use an agent if and only if they own it or hold a grant. Users SHALL be able to list exactly the agents they can use.

#### Scenario: Grant access
- **WHEN** the owner grants a user access to an agent
- **THEN** that user sees the agent in their agent list and can start sessions with it

#### Scenario: Revoke access
- **WHEN** the owner revokes a user's grant
- **THEN** that user can no longer start new sessions with the agent

#### Scenario: Non-owner cannot manage grants
- **WHEN** a granted (non-owner) user attempts to grant or revoke access for others
- **THEN** the system rejects the request as forbidden

### Requirement: Agent access confers retrieval access to its KBs
When a user chats with an agent they can use, retrieval SHALL search all of the agent's KBs as stored, including KBs the chatting user cannot read directly. Direct KB endpoints (listing, document access, upload, delete) SHALL continue to enforce the user's own KB access and SHALL NOT be widened by agent grants.

#### Scenario: Granted user retrieves from a private KB through the agent
- **WHEN** a user chats with a granted agent whose KB set includes a KB the user cannot read directly
- **THEN** retrieval searches that KB and the answer may cite its passages

#### Scenario: Agent grant does not open the KB itself
- **WHEN** a user granted an agent requests the documents of one of the agent's KBs they cannot read directly
- **THEN** the system rejects the request as it does today

### Requirement: Agent deletion
The system SHALL allow the owner to delete an agent that has no chat sessions referencing it, and SHALL reject deletion while sessions reference it.

#### Scenario: Delete unused agent
- **WHEN** the owner deletes an agent with no sessions
- **THEN** the agent and its grants are removed

#### Scenario: Delete is blocked by existing sessions
- **WHEN** the owner attempts to delete an agent that sessions reference
- **THEN** the system rejects the request with a conflict error
