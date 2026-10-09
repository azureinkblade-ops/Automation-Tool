# EA-4E.92FV Result Status Guard

Status: NON-LIVE RESULT-STORE CORRECTION / LIVE HANDOFF HOLD
Baseline: `199a1603751bebeb0dfdf4ea06b37773f197ec2d`
Date: 2026-10-09 (America/Phoenix)

R11 requires a receiver to return `CANCELLED` after cancellation or lease
revocation and forbids promoting an expired or revoked attempt as
`SUCCEEDED`. The result store already read the mutable delegation and lease
rows under `BEGIN IMMEDIATE`, but did not check their status. A fresh success
could therefore be stored and delivered after either event committed.

The store now denies a new `SUCCEEDED` result unless the delegation remains
`CREATED` and the capability lease remains `ACTIVE`. This check runs inside
the result/delivery transaction. A cancellation result remains recordable
after revocation, and an exact result persisted before later cancellation
still replays without creating a second mailbox delivery. Focused tests first
reproduced two failures; after the fix, 37 tests and 6 subtests passed.
The bounded delegation/agent fake-only ladder passed 139 tests and 39
subtests, with zero failures.

This is a durable-status guard, not a trusted terminal verifier. It does not
prove lease expiry against a trusted clock, receiver cooperation, result
payload schema validity, output bytes, or real Codex/Kilo/OpenCode execution.
Those remain separate gates. No receiver, network, Docker, model, GPU,
ComfyUI, or production activation was invoked.

`NEW_SUCCESS_AFTER_CANCELLATION=DENIED`
`NEW_SUCCESS_AFTER_REVOCATION=DENIED`
`CANCELLATION_RESULT_AND_PRIOR_EXACT_REPLAY=PRESERVED`
`PRODUCTION_READY=NO`
