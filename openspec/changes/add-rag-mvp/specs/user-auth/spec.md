## ADDED Requirements

### Requirement: Seeded users and teams
The system SHALL provide users and teams that are created by an administrator or seed process. Self-service registration is out of scope for the MVP. Each user SHALL have a unique identifier, a unique login (email), and a hashed password. Each user SHALL belong to zero or more teams via a membership record.

#### Scenario: Seed creates a user with a team membership
- **WHEN** the seed process runs with a user assigned to a team
- **THEN** the user is persisted with a hashed (never plaintext) password
- **AND** a membership record links the user to that team

#### Scenario: Duplicate login is rejected
- **WHEN** a user is created with an email that already exists
- **THEN** the system rejects the creation and reports a conflict

### Requirement: Password authentication issues a JWT
The system SHALL authenticate a user by verifying the submitted password against the stored hash and, on success, SHALL issue a signed JWT carrying the user's identity and an expiry.

#### Scenario: Successful login
- **WHEN** a user submits a correct email and password
- **THEN** the system returns a signed JWT containing the user id and an expiry claim

#### Scenario: Wrong credentials
- **WHEN** a user submits an incorrect password
- **THEN** the system returns an authentication error and no token

### Requirement: Authenticated request contract
Every non-auth API endpoint SHALL require a valid, unexpired JWT and SHALL resolve the caller's user identity from it. Requests without a valid token SHALL be rejected as unauthorized.

#### Scenario: Missing or invalid token
- **WHEN** a request to a protected endpoint has no token or an invalid/expired token
- **THEN** the system responds with 401 Unauthorized and performs no action

#### Scenario: Valid token resolves identity
- **WHEN** a request carries a valid JWT
- **THEN** the system makes the caller's user id and team memberships available to authorization checks
