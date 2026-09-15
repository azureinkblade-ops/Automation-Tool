# EA-4E.92S Suspended Process Ownership - Partial Implementation

Date: 2026-09-15
Baseline: 6c1934451c2e4cf1389f92f373610e1447742085
Status: IMPLEMENTED / REVIEWED / FAKE-ONLY PASS / UNCOMMITTED
Native containment: NOT QUALIFIED

## Scope

Added `tools/ea4e92s_suspended_process.py` and its focused tests. The helper
accepts only an already-owned profile/security creation-attribute chain and an
injected collaborator. It validates an exact suspended-creation result, including
distinct positive process/thread handles, bounded process/thread IDs, suspended
state, creation-time job binding and creation-time AppContainer binding.

The returned owner retains the borrowed creation owner and owns only the returned
process/thread handles. Cleanup requires confirmed termination before either
handle may close, then closes thread before process. Confirmed cleanup is
idempotent. Ambiguous creation, handle identity, termination or handle closure
raises `UnknownSuspendedProcess`, retains available evidence and blocks retry.
Unproven creation predicates with trustworthy handles are terminated and closed
before a definitive denial.

No command line, environment, bootstrap, native binding, resume path, parser,
SDK, receiver, model, network, GPU, ComfyUI or fallback launcher exists here.
The creation owner remains caller-owned. Job-handle ownership and broker-wide
orchestration remain later work.

## Review Correction

The first implementation attempted thread/process handle closure even when child
termination was not confirmed. Focused review cases reproduced that loss of the
only process reconciliation handle. Cleanup now stops immediately on uncertain
termination and leaves both handles retained in sticky unknown state. The review
also normalized malformed creation-owner inputs to a pre-creation denial. A final
red case found that a missing cleanup collaborator method leaked `AttributeError`;
the corrected path catches that boundary failure, attempts any remaining handle
closure after confirmed termination and returns sticky unknown.

## Verification

Pinned stage2-v2 Python with the existing fake-only, filesystem and non-live host
guards. Initial contract: 37 passed. First review red: 4 failures reproduced the
ownership issues; second review red: 1 failure reproduced the incomplete-
collaborator leak. Final focused result: 40 passed / 0 failed / 0.10s. Complete
92S bounded result: 321 passed / 0 failed / 0.62s. Both tripwire event counts
were zero in each successful bounded run.

Final full fake-only Hermes Core gate: 3916 passed / 35 raw failed / 6 unchanged
OS-test deselections / 104 subtests passed, exit 1, 112.99s. Exact comparison
with the committed Windows-profile baseline found all 35 failure identities
unchanged, added 0 and resolved 0. The 34 attempted process launches were denied;
filesystem events were zero. JUnit SHA256:
`a2f15e5766119c1b8788cce97a26b78a13f937932a71a31eaaed2ca1759c1197`.

Classification: bounded PASS and working-tree NO-NEW-REGRESSIONS PASS; raw gate
NOT GREEN. Exactly three candidate files belong to this slice. They are unstaged,
uncommitted and unpushed. No live or native action occurred.

Next: exact three-file source review and staged-export qualification. Do not bind
a native process adapter, resume a process or claim containment qualification.
