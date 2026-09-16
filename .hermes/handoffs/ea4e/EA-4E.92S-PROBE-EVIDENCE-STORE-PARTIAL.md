# EA-4E.92S Probe Evidence Store Partial

## Scope

This checkpoint implements the non-live durable evidence and broker-death
reconciliation contract required by the Stage 3 envelope. It does not execute a
probe, inspect a process, call a native API, terminate work, open a listener, or
grant launch authority.

## Contract

`tools/ea4e92s_probe_evidence_store.py` owns an explicit-path SQLite store with
schema identity, instance identity and epoch. Every probe binds its envelope,
governing commit, host, request and probe identities; runtime, probe, broker and
target hashes; profile/SID identity; expected outcome; and the one-attempt
budget.

The state machine is:

`PREPARED -> STARTED -> PASSED | FAILED | UNKNOWN`

`UNKNOWN` is durable and blocks every later preparation or start. It may move
only to `RECONCILED_CLEAN` after an injected observation names the exact durable
job/process/thread identities, confirms cleanup, and reports zero surviving
owned processes. Non-clean observations remain `UNKNOWN`; a later observation
must advance monotonically. Exact replay is idempotent and divergent replay is
denied.

Raw worker output is not stored and cannot grant authority. The store records
only a SHA256 identity for the observed result. Cleanup observations are values
provided by a future reviewed native controller; this module cannot discover or
act on resources itself.

## Safety Boundary

- native probe execution: not authorized and not performed;
- process creation/termination: zero;
- native API calls: zero;
- network/listener activity: zero;
- receiver/model/browser/GPU/ComfyUI activity: zero;
- retries: zero;
- machine-wide cleanup: impossible through this module.

The remaining native blockers are the concrete suspended-process/resume/capture
adapter, native pre-resume query adapter, immutable machine profile/ACL proof,
instantiated harness fixtures, and the separately reviewed controller that will
produce the value observations accepted by this store.

## Verification

- focused store contract: 27 passed / 0 failed;
- bounded EA-4E.92S chain: 543 passed / 0 failed;
- full guarded Hermes Core: 4,156 passed / 35 inherited failures / 6
  deselected / 104 subtests passed;
- exact inherited-failure identity comparison: 35 versus 35, exact match;
- full-run JUnit SHA256:
  `70b0e353941b2ec62937fd7f7d17f59648dc1ae78963f91379ee8c058061a98d`;
- fake-only denied process attempts: 32;
- filesystem tripwire events: 0;
- prohibited runtime-capability scan: pass;
- whitespace validation: pass.

State: PROBE EVIDENCE STORE IMPLEMENTED / NON-LIVE QUALIFICATION PASS / NOT
STAGED / NOT COMMITTED / NOT PUSHED / NATIVE EXECUTION HOLD. No probe ran and
no resource was inspected, created, contacted, terminated or cleaned.

## Staged Qualification

Exactly this implementation, focused test and evidence file were staged. The
first immutable staged export used tree
`ff3720576ab2abf7c6fdb116cf8893a18c129017`; archive SHA256
`c3eb5b046371bbf61477781165e410ff662ddcc3a8868d99ee7de7cc9907217f`.
The extracted tree passed the complete bounded EA-4E.92S chain: 543 passed / 0
failed, with fake-only and filesystem tripwire events both zero.

The evidence file was then normalized with these measured staged-export
results. A final staged tree/export is required before commit so the frozen
artifact includes its own qualification record.
