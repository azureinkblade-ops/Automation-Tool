---
title: Hermes EA-4A Execution Authorization Claim Domain and Atomic Claim Persistence
date: 2026-08-13
milestone: EA-4A
disposition: PASS
scope: ExecutionClaim domain artifact + claim linkage/hash/version semantics + claim-time Authorization validity checks + claimant identity + claimed_at/claim_expires_at + claim storage + claim lookup + claim ledger event + atomic claim transaction + replay/idempotency/conflict handling + integrity verification
capability_created: "ExecutionClaim (first durable execution claim)"
forbidden_scope: "ExecutionAttempt, authorization execution, WorkerRouter, worker launch, enqueue, dispatch, subprocess, EXECUTING, app.py integration, automatic claim after issuance"
schema_version: "4"
invariant_preserved: "ACCEPTED != EXECUTION AUTHORIZATION ; AUTHORIZED != CLAIMED != EXECUTING"
tests_ea4a_focused: "29/29 PASS"
tests_ea3i2_regression: "21/21 PASS"
tests_ea3i1_regression: "19/19 PASS"
tests_ea3a_regression: "55/55 PASS"
tests_ea3b_regression: "40/40 PASS"
full_hermes_core: "448/448 PASS (in-process loader; test_phase6_end_to_end separate 17/17)"
mutation_teeth: "5/5 PASS (byte-exact restore)"
claim_read_tamper: "PASS (get_claim fails closed on claim_linkage_sha256 tamper; verify_integrity false)"
concurrency_proof: "PASS (two-connection/thread race: same-claimant idempotent first-writer-wins, different-claimant CONFLICT; exactly one CLAIM_RECORDED; lost-racer UNIQUE violation converted to domain outcome, no raw sqlite3 error)"
capability_scan: "BLOCK (no ExecutionAttempt/WorkerRouter/launch/enqueue/dispatch/subprocess/EXECUTING tokens in claim/domain/store)"
db_tracked: "NO"
production_db_present: "NO"
remote_state: "LOCAL ONLY (not pushed; push requires separate pre-push audit authorization)"
unrelated_edits_preserved: "YES"
---

# Hermes EA-4A Execution Authorization Claim Domain and Atomic Claim Persistence

## Authorization record

**AUTH-2026-08-13 Hermes EA-4A Claim Domain and Atomic Claim Persistence**

Authorized scope:

- ExecutionClaim domain artifact
- claim linkage/hash/version semantics
- claim-time Authorization validity checks (existence, integrity, unexpired)
- claimant identity (structured)
- claimed_at + claim_expires_at (absolute UTC Z, bounded non-null)
- claim storage
- claim lookup
- claim ledger event (CLAIM_RECORDED)
- atomic claim transaction (one BEGIN IMMEDIATE ... COMMIT)
- replay/idempotency/conflict handling
- integrity verification (read-path + verify_integrity)

Forbidden scope:

- ExecutionAttempt
- authorization execution
- WorkerRouter
- worker launch
- enqueue
- dispatch
- subprocess
- EXECUTING
- app.py integration
- automatic claim after issuance

## Result

EA-4A is COMPLETE: the first durable ExecutionClaim is created only through the
validated flow (replay check, Authorization existence/integrity/unexpired
prerequisite, bounded claim lifetime, one-Claim-per-Authorization enforcement,
atomic persistence with CLAIM_RECORDED, read-path tamper detection). Authority
DB schema advanced to v4; old/unsupported versions fail closed; no silent
migration.

29 focused EA-4A tests + 5 mutation teeth all PASS with byte-exact source
restoration. Full comparable Hermes core: 448/448 PASS (in-process loader;
test_phase6_end_to_end runs separately, 17/17). Concurrency is proven by two
real two-connection/two-thread claim-race tests (same-claimant idempotent
first-writer-wins, different-claimant CONFLICT, exactly one CLAIM_RECORDED,
lost-racer UNIQUE violation converted to the domain outcome, no raw
sqlite3.IntegrityError exposed). No ExecutionAttempt, no WorkerRouter, no worker
launch/enqueue/dispatch, no subprocess, no EXECUTING, no app.py integration, no
automatic claim after issuance.

Stop condition met. EA-4B (claim consumption / execution attempt) remains
separately authorized and was not begun.
