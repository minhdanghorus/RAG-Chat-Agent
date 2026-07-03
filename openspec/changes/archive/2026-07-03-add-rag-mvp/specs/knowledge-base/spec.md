## ADDED Requirements

### Requirement: Knowledge base ownership
The system SHALL support knowledge bases (KBs) owned by either a single user (personal) or a team (shared). A KB SHALL have a name and exactly one owner reference that is either a user or a team.

#### Scenario: Create a personal KB
- **WHEN** an authenticated user creates a KB as personal
- **THEN** the KB is persisted with the caller as its user owner

#### Scenario: Create a team KB
- **WHEN** an authenticated user who is a member of a team creates a KB owned by that team
- **THEN** the KB is persisted with that team as its owner

#### Scenario: Cannot create a team KB for a team you are not in
- **WHEN** a user attempts to create a KB owned by a team they are not a member of
- **THEN** the system rejects the request as forbidden

### Requirement: Access resolution
The system SHALL resolve the set of KBs a user may access as the union of the user's personal KBs and the KBs owned by any team the user belongs to. A user SHALL only be able to list KBs within this resolved set.

#### Scenario: Listing returns only accessible KBs
- **WHEN** a user requests the KB list
- **THEN** the response contains their personal KBs and their teams' KBs
- **AND** contains no KB owned by another user or a team they do not belong to

### Requirement: Manage permission
The system SHALL restrict uploading documents to and deleting a KB to the KB's owner: the owning user for a personal KB, or any member of the owning team for a team KB. Members with read access SHALL be able to read and chat but SHALL NOT delete the KB.

#### Scenario: Owner deletes a KB
- **WHEN** the owner (or an owning-team member) deletes their KB
- **THEN** the KB and its documents and chunks are removed

#### Scenario: Non-owner cannot delete
- **WHEN** a user who is not the owner (nor an owning-team member) attempts to delete a KB
- **THEN** the system rejects the request as forbidden and the KB is unchanged

### Requirement: KB isolation is the retrieval boundary
The system SHALL tag every stored chunk with the `kb_id` of the KB it belongs to, and SHALL treat `kb_id` as the authoritative isolation key for all retrieval. No retrieval SHALL return chunks from a KB outside the caller's resolved access set.

#### Scenario: Chunks carry their KB id
- **WHEN** a document is ingested into a KB
- **THEN** every chunk produced is stored with that KB's `kb_id`

#### Scenario: Cross-KB leakage is impossible via access set
- **WHEN** any retrieval is performed for a user
- **THEN** the candidate chunk set is constrained to `kb_id` values within the user's resolved access set
