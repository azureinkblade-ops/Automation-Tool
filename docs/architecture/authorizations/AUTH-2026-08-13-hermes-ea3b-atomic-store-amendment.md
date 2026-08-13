---
title: "AUTH-2026-08-13 Hermes EA-3B Atomic Store Amendment"
document_id: "AUTH-2026-08-13-HERMES-EA3B-ATOMIC-STORE-AMENDMENT"
version: "0.1.0"
status: "proposed"
owner: "Hermes Agent"
date: "2026-08-13"
source_milestone: "Hermes EA-3B Atomic Store Amendment Authorization"
reference_commits:
  - "df5134b Clarify execution authorization time semantics"
  - "4ccff94 Add Hermes execution authorization domain model (EA-1)"
  - "a09981e Add Hermes execution authority persistence (EA-2)"
  - "1ba7a19 Design Hermes execution authorization issuance (EA-3D)"
  - "7e7afe6 Bind Hermes authorization to request and decision (EA-3A)"
authorized_scope:
  - "Persistence-contract strengthening only (no issuance capability)"
  - "Atomic store method record_granted_decision_and_authorization(decision, authorization)"
  - "Single SQLite transaction: decision row + DECISION_RECORDED + authorization row + AUTHORIZATION_RECORDED"
  - "Fail-closed cross-artifact consistency checks (storage-only, no authority decision)"
  - "Request prerequisite (persisted request must exist; hash + task identity must agree)"
  - "Request-keyed reads get_decision_for_request / get_authorization_for_request"
  - "UNIQUE(request_id) per request for decisions and authorizations"
  - "Standalone record_decision(GRANTED) and record_authorization() rejected (bypass eliminated)"
  - "DENIED decisions persist via record_decision (one terminal decision per request)"
  - "Idempotent identical grant replay; conflicting replay fails closed"
  - "request_linkage_sha256 tamper envelope (decisions + authorizations)"
  - "verify_integrity extends to request_id physical-vs-canonical, uniqueness, orphan detection"
  - "Authority DB schema 2 -> 3; v1/v2 fail closed; NO silent migration / NO auto-migrate"
forbidden_scope:
  - "Authorization issuance service (ExecutionAuthorizationService / AuthorizationIssuanceService)"
  - "grant_execution_authorization / issue_execution_authorization / authorize"
  - "policy evaluator with grant capability"
  - "human approval adapter / policy-service adapter"
  - "ExecutionClaim / ExecutionAttempt / authorization consumption / attempt consumption"
  - "WorkerRouter / worker launch / enqueue / dispatch"
  - "AUTHORIZED_FOR_EXECUTION / EXECUTING transitions"
  - "evaluate governance acceptance / actor authority / authorization policy / expiry / nonce (belongs to EA-3I)"
tests_ea3b_focused:
  count: 20
  result: PASS
tests_ea3a_regression:
  count: 55
  result: PASS
tests_ea2_store_regression:
  count: 17
  result: PASS
full_hermes_core:
  count: 379
  result: PASS
mutation_teeth:
  tooth_1: "decision_hash cross-check removal -> mismatch test fails: PASS (byte-exact restore)"
  tooth_2: "rollback commit split -> rollback-injection test fails: PASS (byte-exact restore)"
capability_scan:
  operational_match: "BLOCK (no ExecutionAuthorizationService/grant/issue/ExecutionClaim/WorkerRouter/AUTHORIZED_FOR_EXECUTION/EXECUTING)"
production_python_changed:
  - "tools/hermes_core/execution_authorization_store.py"
  - "tools/hermes_core/sqlite_execution_authorization_store.py"
disposition: "PASS (local commit only; not pushed)"
---

# AUTH-2026-08-13 Hermes EA-3B Atomic Store Amendment

This record authorizes and attests the EA-3B atomic store amendment: a
persistence-contract strengthening milestone only. It closes the EA-3D-identified
gap where a GRANTED decision and its authorization could be persisted via
separate operations, leaving a half-grant state.

## Authorized scope

EA-3B introduces atomic grant persistence and request-keyed lookup primitives
required by the frozen EA-3D issuance design. The atomic method persists a
GRANTED `ExecutionAuthorizationDecision` together with its
`ExecutionAuthorization` in one SQLite transaction, with fail-closed
cross-artifact consistency checks. It validates that already-built immutable
artifacts are mutually consistent enough to persist together. It does NOT decide
whether the grant is justified, whether an actor may approve, whether policy
allows scope, whether governance acceptance is valid, or any other authority
question. Those belong to EA-3I.

## Forbidden scope

No issuance service, policy evaluator with grant capability, claim, attempt,
worker behavior, or execution transition was introduced. The capability scan
over the two changed modules returns only documentation/negative comments (every
operational match is BLOCK).

## Verification

- 20 focused EA-3B store tests PASS (atomic success, mismatch matrix with
  zero-write guarantee, missing/wrong request, denied-then-grant, idempotent /
  conflicting replay, request-keyed read + tamper, rollback-injection
  zero-residue, standalone bypass elimination, DENIED standalone, orphan
  detection, concurrency, 2 schema-version tests).
- EA-3A domain/schema regression 55/55 PASS; EA-2 store regression 17/17 PASS.
- Full hermes_core suite 379/379 PASS.
- Two mutation teeth (decision_hash cross-check removal; rollback commit split)
  each make a dedicated test fail, with byte-exact source restoration.
- `git diff --check` clean; no `.db` tracked; no production `execution_authority.db`
  created by tests.

## Schema discipline

Authority DB schema advanced `2 -> 3` because EA-3B adds physical `request_id`
columns (UNIQUE) plus `request_linkage_sha256` envelopes to the decisions and
authorizations tables. Opening a pre-EA-3B (EA-3A) schema-v2 DB, or a
pre-EA-3A schema-v1 DB, fails closed via `ExecutionAuthorizationSchemaError`.
There is NO silent migration and NO auto-migrate; `CREATE TABLE IF NOT EXISTS`
never runs against an unknown/old DB.

## Invariant

```text
ACCEPTED != EXECUTION AUTHORIZATION
```

Preserved. The store strengthens persistence integrity only; it creates no
authority decision and no execution capability.

Disposition: PASS. Commit is local `main` only; push requires a separate
pre-push audit + remote checkpoint authorization.
