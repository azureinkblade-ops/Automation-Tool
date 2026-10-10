# EA-4E.92GL Codex Terminal Observation Time

Status: NON-LIVE REGISTRY CHECKPOINT / RESULT DELIVERY HOLD
Baseline: `4e971587e7aaf645fb8f3da0c0b2b80c8d2328bb`
Date: 2026-10-09 (America/Phoenix)

The Codex transport registry now writes `terminal_observed_at` in the same
SQLite transition that stores a terminal state and result. A terminal row
cannot be transitioned again through the registry API. The returned record
exposes the observation time after restart. The durable Codex ping witness
denies a verified result without a finite positive terminal observation.

Registry schema v2 migrates v1 by adding a nullable column. Existing v1
terminal rows are deliberately left NULL; their historical `updated_at`
cannot be treated as completion time because it was mutable. Such rows
remain ineligible for the no-output ping witness. This does not backfill
time, rerun Codex, or change the pinned executable.

The focused fake-only timestamp/witness gate passed 22 tests before the
additional missing-time case. The bounded cross-agent/start/result ladder
passed 175 tests with exactly two real-binary presence checks deselected.
An unfiltered Codex gate reported 113 passed and two failed because the
historically pinned Codex executable is absent; those failures are retained.

This timestamp is a trusted registry observation, not proof of the OS's
exact process-exit instant or an attested image-section byte identity. No
Codex result/mailbox delivery host was added. The next non-live slice must
bind this durable observation to a canonical Codex ping result and the
transactional result/mailbox return, with cancellation and lease checks.
The installed successor binary still requires separate exact qualification
before any real Codex invocation.

`CODEX_TERMINAL_OBSERVATION=PASS_FAKE_ONLY`
`LEGACY_TERMINAL_BACKFILL=NO`
`CODEX_RESULT_DELIVERY=HOLD`
`LIVE_CODEX_INVOCATION_AUTHORIZED=NO`
`PRODUCTION_READY=NO`
