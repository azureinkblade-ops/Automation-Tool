---
title: "AUTH-2026-08-12 Hermes EA-1 Execution Authorization Domain Model"
document_id: "AUTH-2026-08-12-HERMES-EA1-EXECUTION-AUTHORIZATION-DOMAIN-MODEL"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
related_design:
  - "docs/architecture/hermes-execution-authorization-handoff.md"
  - "docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md"
  - "docs/architecture/decisions/ADR-0004-acceptance-vs-execution.md"
---

# Authorization Record — Hermes EA-1 Execution Authorization Domain Model

## Authorization granted

This milestone authorizes **EA-1 — Execution Authorization Domain Model +
Schemas**, a **structural/domain-model-only** milestone.

## Scope authorized (implemented in this milestone)

- Immutable domain artifacts:
  - `ExecutionAuthorization`
  - `ExecutionAuthorizationRequest`
  - `ExecutionAuthorizationDecision`
- Structured supporting domain types:
  - `ExecutionAuthorizationScope`
  - `ExecutionAuthorizationActor`
  - `ExecutionAuthorizationPolicyRef`
- Constrained enums:
  - `ExecutionAuthorizationActorType` (HUMAN / POLICY_SERVICE / SYSTEM)
  - `ExecutionAuthorizationDecisionOutcome` (GRANTED / DENIED)
- Domain validation, canonical serialization, deterministic hashing,
  hash self-verification.
- YAML schemas `hermes.execution_authorization[_request|_decision]` under
  `docs/architecture/schemas/`.
- Focused domain + schema-parity + hashing + negative + mutation-tooth tests.
- Module: `tools/hermes_core/execution_authorization.py` (pure domain, no
  SQLite / runtime / worker / filesystem / clock dependencies).

## Explicit non-scope (prohibited in this milestone)

- `execution_authority.db` / `ExecutionAuthorizationStore` / SQLite authority
  persistence.
- Authorization issuance / grant / revocation persistence.
- `ExecutionClaim` / `ExecutionAttempt` / `WorkerRouter`.
- Worker launch / enqueue / dispatch.
- `AUTHORIZED_FOR_EXECUTION` / `EXECUTING` / `AWAITING_EXECUTION_AUTHORIZATION`
  transitions.
- `ExecutionAuthorizationIntegrityError` (reserved for EA-2 persisted-tamper
  semantics); EA-1 uses only `ExecutionAuthorizationError(ValueError)` /
  `ExecutionAuthorizationValidationError(ValueError)`.
- Any production code that consumes an `ExecutionAuthorization` to grant
  authority. `ACCEPTED != EXECUTION AUTHORIZATION` is preserved.

## Required next steps remain unauthorized

EA-2 (persistence), EA-3 (issuance — first real execution-capability phase),
EA-4 (claims), EA-5 (integration), EA-6 (worker router), EA-7 (e2e proof) each
require separate, explicit authorization before implementation.

## Verification

- Domain + schema + hashing + negative + mutation-tooth tests: PASS.
- Full Hermes core suite: 323/323 PASS.
- `git diff --check`: CLEAN.
- No production `.db` tracked.
- No `app.py` / `automation_state.db` change.
- Mutation source restored byte-exactly.

## Status

EA-1 complete and committed to local `main` (design + domain + schemas).
Not yet pushed (per milestone stop condition).
