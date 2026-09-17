# EA-4E.92S Reconciliation Controller Partial

## Scope

This checkpoint implements one-shot, non-live orchestration between the durable
probe-evidence store and a future reviewed NQ-12 owned-resource observer. It
does not implement that observer or perform native inspection, launch, cleanup,
network, receiver, model, browser, GPU or ComfyUI activity.

## Contract

The controller accepts only the exact probe-evidence store and an NQ-12 record
in durable `UNKNOWN` state with previously stored job/process/thread IDs. It
invokes the injected observer at most once with those exact IDs, accepts only an
exact `BrokerDeathObservation`, and delegates all identity, monotonic-time,
cleanup and survivor projection to the durable store.

Observer absence, exceptions or malformed evidence leave the durable record
unknown. A non-clean observation is persisted as unknown without retry. A later
controller invocation may submit a newer observation. Once the record reaches
`RECONCILED_CLEAN`, exact controller replay returns the durable result without
calling the observer again.

## Safety Boundary

- native observer: not implemented;
- native probe execution: not authorized and not performed;
- native/process/network calls: zero;
- observer calls per controller invocation: at most one;
- automatic retries: zero;
- launch or cleanup authority: none.

Native containment remains not qualified. Remaining blockers include the
concrete native process/resume/capture and pre-resume query adapters, immutable
machine profile/ACL proof, instantiated harness fixtures, and the separately
reviewed native observer implementation.

## Verification

- focused controller contract: 19 passed / 0 failed;
- bounded EA-4E.92S chain: 562 passed / 0 failed;
- full guarded Hermes Core: 4,175 passed / 35 inherited failures / 6
  deselected / 104 subtests passed;
- exact inherited-failure identity comparison: 35 versus 35, exact match;
- full-run JUnit SHA256:
  `4af25416f719fcd5af523172e1d26d1ee99ad088a99caa3314d60843502e2187`;
- fake-only denied process attempts: 32;
- filesystem tripwire events: 0;
- prohibited runtime-capability scan: pass;
- whitespace validation: pass.

State: RECONCILIATION CONTROLLER IMPLEMENTED / NON-LIVE QUALIFICATION PASS /
NOT STAGED / NOT COMMITTED / NOT PUSHED / NATIVE EXECUTION HOLD. No native
observer or probe ran and no resource was inspected, created, contacted,
terminated or cleaned.

## Staged Qualification

Exactly this controller, focused test and evidence file were staged. Immutable
tree `16ae2768ccb8149736ff44ce4545aea4cea99ebf`; archive SHA256
`2c30c596110443e8a935c3dd95c7025312b6dee4d1573a043446b65dbc72fdaa`.
The extracted tree passed the complete bounded EA-4E.92S chain: 562 passed / 0
failed, with fake-only and filesystem tripwire events both zero.

State: EXACT THREE-FILE CHECKPOINT STAGED / FIRST STAGED-EXPORT
QUALIFICATION PASS / EVIDENCE NORMALIZATION IN PROGRESS / NOT COMMITTED / NOT
PUSHED / NATIVE EXECUTION HOLD. No native observer, probe or resource action
occurred.
