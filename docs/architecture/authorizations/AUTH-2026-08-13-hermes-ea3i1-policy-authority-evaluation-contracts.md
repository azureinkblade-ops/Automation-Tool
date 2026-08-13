---
title: Hermes EA-3I.1 Policy and Authority Evaluation Contracts
date: 2026-08-13
milestone: EA-3I.1
disposition: PASS
scope: pre-capability policy + authority evaluation contracts
capability_created: NONE
invariant_preserved: "ACCEPTED != EXECUTION AUTHORIZATION"
tests_ea3i1_focused: "19/19 PASS"
tests_ea3a_regression: "55/55 PASS"
tests_ea3b_store_regression: "40/40 PASS"
full_hermes_core: "398/398 PASS"
mutation_teeth: "3/3 PASS (byte-exact restore)"
capability_scan: "CLEAN (docstring/negative prose only)"
production_python_changed: "yes (two new modules + policies dir + test + helper)"
git_diff_check: "CLEAN"
db_tracked: "NO"
production_db_present: "NO"
remote_state: "LOCAL ONLY (not pushed; push requires separate pre-push audit authorization)"
unrelated_edits_preserved: "YES"
---

# Hermes EA-3I.1 Policy and Authority Evaluation Contracts

## Authorization record

**AUTH-2026-08-13 Hermes EA-3I.1 Policy and Authority Evaluation Contracts**

Authorized scope:

- policy evaluation contracts
- actor authentication/authority validation contracts
- deterministic policy resolution
- ALLOW / DENY / REQUIRES_HUMAN evaluation
- scope constraint evaluation (attempt/runtime ceilings; never widen)
- read-only acceptance prerequisite validation
- tests
- docs

Forbidden scope:

- persisted Decision
- persisted ExecutionAuthorization
- record_granted_decision_and_authorization invocation
- issuance service
- ExecutionClaim
- ExecutionAttempt
- WorkerRouter
- execution state transitions

## Result

EA-3I.1 is functionally COMPLETE as a pre-capability evaluation slice. It
defines deterministic, versioned policy contracts and a pure/read-only
evaluation function. It creates zero real execution authorization.

- Policy decision enum: `ALLOW` / `DENY` / `REQUIRES_HUMAN` (explicit, none
  create authority).
- HUMAN: eligible only when authenticated + recognized role; otherwise
  fail-closed (authority error) or DENY.
- POLICY_SERVICE: requires explicit human decision unless an (operation,
  worker_class) is enumerated in `auto_scopes` (default NONE) -> `REQUIRES_HUMAN`.
- SYSTEM: can never grant by default -> `DENY`.
- Unknown operation -> DENY (fail closed).
- Unknown worker_class -> DENY (fail closed).
- `worker_class = None` -> deferred/unresolved, NOT unrestricted ->
  `REQUIRES_HUMAN`.
- Scope widening: impossible; attempt/runtime ceilings CONSTRAIN, never widen;
  `input_hash` preserved.
- Acceptance prerequisite: read-only `verify_acceptance_prerequisite(request,
  acceptance)` compares
  `request.accepted_governance_artifact_id == acceptance.acceptance_id`,
  `request.accepted_governance_hash == acceptance.acceptance_sha256`,
  `request.task_id == acceptance.task_id`, and `acceptance.is_accepted() ==
  True`. Any mismatch is an ERROR (never downgraded to DENY). ACCEPTED is a
  prerequisite only; it does NOT imply authorization.
- Determinism: identical immutable (request, actor_context, policy) inputs yield
  identical results. No wall-clock, randomness, or mutable global policy state.
- Persistence: the evaluator never imports the execution-authority store, never
  persists anything, never constructs a capability-bearing Decision or
  ExecutionAuthorization, never generates nonce / issued_at / expires_at.
- Negative-capability tests + AST capability scan prove no issuance/claim/worker
  behavior exists in the evaluation code.
- Three mutation teeth (POLICY_SERVICE default -> ALLOW; remove authority-role
  validation; scope widening) each kill a targeted test, with byte-exact source
  restoration.

## Files changed

- `tools/hermes_core/execution_authorization_policy.py` (new)
- `tools/hermes_core/execution_authorization_evaluation.py` (new)
- `tools/hermes_core/policies/ea-baseline.yaml` (new)
- `tests/hermes_core/test_execution_authorization_evaluation.py` (new)
- `tests/hermes_core/test_execution_authorization_store.py` (helper
  `make_acceptance_artifact_for_request` only)
- `docs/architecture/hermes-execution-authorization-issuance.md` (EA-3I.1 COMPLETE note)
- `docs/architecture/hermes-execution-authorization-handoff.md` (`## 29.3` section)
- `docs/architecture/README.md` (line 59 EA-3I.1 status)
- `docs/architecture/authorizations/AUTH-2026-08-13-hermes-ea3i1-policy-authority-evaluation-contracts.md` (this record)

## Disposition

PASS. Stop condition met: local commit only, not pushed. Do not begin EA-3I.2.
