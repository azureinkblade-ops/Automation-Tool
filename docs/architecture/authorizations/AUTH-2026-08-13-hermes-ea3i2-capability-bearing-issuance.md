---
title: Hermes EA-3I.2 Capability-Bearing Execution Authorization Issuance
date: 2026-08-13
milestone: EA-3I.2
disposition: PASS
scope: capability-bearing execution authorization issuance
capability_created: "ExecutionAuthorizationDecision + ExecutionAuthorization (real authority)"
invariant_preserved: "ACCEPTED != EXECUTION AUTHORIZATION"
tests_ea3i2_focused: "21/21 PASS"
tests_ea3i1_regression: "19/19 PASS"
tests_ea3a_regression: "55/55 PASS"
tests_ea3b_store_regression: "40/40 PASS"
full_hermes_core: "419/419 PASS"
mutation_teeth: "5/5 PASS (byte-exact restore)"
capability_scan: "BLOCK (no ExecutionClaim/ExecutionAttempt/WorkerRouter/worker/execution-state tokens)"
production_python_changed: "yes (one new module execution_authorization_issuance.py + test + store-test helper)"
git_diff_check: "CLEAN"
db_tracked: "NO"
production_db_present: "NO"
remote_state: "LOCAL ONLY (not pushed; push requires separate pre-push audit authorization)"
unrelated_edits_preserved: "YES"
---

# Hermes EA-3I.2 Capability-Bearing Execution Authorization Issuance

## Authorization record

**AUTH-2026-08-13 Hermes EA-3I.2 Capability-Bearing Issuance**

Authorized scope:

- persisted `ExecutionAuthorizationRequest` retrieval (`store.get_request`)
- exact `AcceptanceArtifact` prerequisite verification (governance read only)
- actor authentication / authority-role validation
- deterministic policy resolution from the request's exact policy reference
- EA-3I.1 evaluator reuse (no duplicated policy logic)
- DENIED Decision persistence (`record_decision`)
- GRANTED Decision + ExecutionAuthorization construction (EA-3A acyclic Model A)
- EA-3B atomic persistence (`record_granted_decision_and_authorization`)
- injected UTC clock seam, non-null `expires_at > issued_at`, `secrets.token_hex` nonce
- replay / idempotency handling (existing terminal evidence returned, no new nonce)
- focused tests + 5 mutation teeth + docs

Forbidden scope (enforced, not crossed):

- `ExecutionClaim`
- `ExecutionAttempt`
- authorization consumption
- `WorkerRouter` / worker launch / enqueue / dispatch
- execution state (`AUTHORIZED_FOR_EXECUTION` / `EXECUTION_CLAIMED` / `EXECUTING`)
- `app.py` integration / automatic issuance trigger
- governance mutation (read-only acceptance verification)

## Disposition

**PASS.** EA-3I.2 is the first milestone permitted to create real execution
authority. It issues durable, replay-safe, policy-bound execution authorization
evidence under the EA-3D / EA-3A / EA-3B / EA-3I.1 contracts and stops there.
The absolute invariant `ACCEPTED != EXECUTION AUTHORIZATION` is preserved. EA-4
(claim/consumption) remains separately authorized.
