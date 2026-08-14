---
title: Hermes EA-4B Execution Claim Consumption and Execution Attempt
date: 2026-08-14
milestone: EA-4B
disposition: PASS
scope: ExecutionAttempt domain artifact + attempt linkage/hash/version semantics + attempt-time Claim validity checks + structured attempt actor identity + attempt storage + attempt lookup + ATTEMPT_RECORDED ledger event + atomic claim-to-attempt consumption + replay/idempotency/conflict handling + attempt-limit enforcement + attempt numbering + must_start_by derivation + read-path tamper detection + concurrency proof + rollback atomicity
capability_created: "ExecutionAttempt (first durable execution attempt)"
forbidden_scope: "authorization execution, WorkerRouter, worker launch, enqueue, dispatch, subprocess, EXECUTING, RUNNING, STARTED, app.py integration, multiple Claims per Authorization"
schema_version: "5"
artifact_version: "ExecutionAttempt artifact version 1"
attempt_status: "RECORDED (exactly one pre-execution status; no reachable EXECUTING/RUNNING/STARTED)"
invariant_preserved: "ACCEPTED != AUTHORIZED != CLAIMED != EXECUTION_ATTEMPT_RECORDED != EXECUTING"
tests_ea4b1_domain: "52/52 PASS"
tests_ea4b2_persistence: "49/49 PASS"
tests_ea4b3_consume: "21/21 PASS"
tests_ea4b4_concurrency: "17/17 PASS"
tests_ea4a_concurrency: "29/29 PASS"
tests_ea4a_store: "40/40 PASS"
tests_ea3i2_regression: "21/21 PASS"
tests_ea3i1_regression: "19/19 PASS"
tests_ea3a_regression: "55/55 PASS"
tests_ea3b_regression: "40/40 PASS"
tests_phase6_e2e: "17/17 PASS"
full_hermes_core: "587/587 PASS"
mutation_teeth: "6/6 PASS (claim expiry bypass, attempt ceiling bypass, claim lineage bypass, rollback split, actor conflict bypass, attempt-number bypass; all byte-exact SHA-256 restoration)"
concurrency_proof: "PASS (500 genuine two-connection/two-thread contention trials: 250 same-actor + 250 different-actor, zero failures; rollback injection after INSERT leaves zero residue, post-rollback recovery produces attempt_number=1)"
capability_scan: "CLEAN (no WorkerRouter/worker launch/enqueue/dispatch/subprocess/EXECUTING/RUNNING/STARTED tokens in attempt/domain/store/consume)"
db_tracked: "NO"
production_db_present: "NO"
remote_state: "LOCAL ONLY (not pushed; push requires separate pre-push audit authorization)"
unrelated_edits_preserved: "YES"
---

# Hermes EA-4B Execution Claim Consumption and Execution Attempt

## Authorization record

**AUTH-2026-08-14 Hermes EA-4B Execution Claim Consumption and Execution Attempt**

Authorized scope:

- ExecutionAttempt domain artifact (immutable frozen dataclass)
- ExecutionAttemptActor (structured identity: actor_id + actor_type + actor_context)
- attempt linkage/hash/version semantics
- attempt-time Claim validity checks (existence, integrity, not expired)
- bounded must_start_by derivation (clamped to claim expiry)
- attempt storage (schema v5)
- attempt lookup (by id, by authorization, by claim)
- ATTEMPT_RECORDED ledger event
- atomic claim-to-attempt consumption (one BEGIN IMMEDIATE transaction)
- replay/idempotempotency/conflict handling (full structured actor identity match required for replay)
- attempt-limit enforcement (derived from Authorization scope, NOT caller-supplied)
- monotonic attempt numbering
- read-path tamper detection (23 physical columns)
- concurrency proof (500 trials)
- rollback atomicity (injected fault after INSERT proves zero residue)

Forbidden scope:

- Multiple Claims per Authorization (frozen UNIQUE(authorization_id) constraint)
- authorization execution
- WorkerRouter
- worker launch
- enqueue
- dispatch
- subprocess
- EXECUTING
- RUNNING
- STARTED
- app.py integration
- caller-supplied attempt_limit

## Result

EA-4B is COMPLETE: the first durable ExecutionAttempt is created only through
the validated flow (replay check with full structured actor identity, Claim
existence/integrity/unexpired prerequisite, Authorization existence/integrity,
attempt ceiling derived from scope, monotonic numbering, bounded must_start_by,
atomic persistence with ATTEMPT_RECORDED, read-path tamper detection for 23
physical columns). Authority DB schema advanced to v5; old/unsupported versions
fail closed; no silent migration.

52 EA-4B.1 domain + 49 EA-4B.2 persistence + 21 EA-4B.3 consume + 17 EA-4B.4
concurrency tests all PASS. Full comparable Hermes core: 587/587 PASS.

### Architecture findings

**Single Claim per Authorization:** The frozen Claim model enforces
UNIQUE(authorization_id) on the execution_authorization_claims table. Only one
Claim can exist per Authorization at a time. Same-Claim consumption is
idempotent replay (full structured actor identity required). Therefore the
normal Claim-consumption service path can produce at most ONE Attempt per
Authorization.

**attempt_limit > 1:** Schema-supported (UNIQUE(authorization_id,
attempt_number) accepts multiple attempt_numbers per Authorization) but NOT
reachable through normal Claim consumption. Multi-Attempt-per-Authorization
would require architecture changes (removing UNIQUE(authorization_id) on
claims, or introducing multi-claim lifecycles). This is by design, not a
defect.

**Claim expiry:** Inclusive boundary (now <= claim_expires_at is valid).

**must_start_by:** Defaults to claim expiry; caller-supplied window clamped
to claim expiry; non-positive windows rejected.

**Rollback atomicity:** Injected failure after Attempt INSERT but before
ATTEMPT_RECORDED leaves zero residue (no partial write). Next valid consume
recovers the slot as attempt_number=1.

Stop condition met. EA-4B is COMPLETE locally. Remote push requires separate
pre-push audit authorization.
