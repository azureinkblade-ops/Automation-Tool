# EA-4E.92GK Codex Durable Terminal Witness

Status: NON-LIVE READ-ONLY RECOVERY / RESULT DELIVERY HOLD
Baseline: `ae92d53ebb177a18df6091077af9ba0cd04ba56c`
Date: 2026-10-09 (America/Phoenix)

`load_codex_terminal_candidate()` reads the Codex transport registry after
restart, reconstructs the persisted process result, verifies the JSONL and
final structured output, matches process PID and the durable STARTED
delegation/launch/one-send/runtime identities, and validates the exact
no-output ping payload against the accepted receipt. It performs no Codex
invocation, no result write, and no mailbox delivery. A missing, forged,
nonzero-exit, or divergent terminal artifact denies.

The focused fake-only suite passed 19 tests. A broader run collected 349
tests and reported 347 passed, 2 failed, 26 subtests passed. Both failures
were existing real-binary presence checks in `test_codex_adapter.py`:
the pinned `bffc5354119c8421/codex.exe` is absent. The pinned path still
names `codex-cli 0.154.0-alpha.6.2` with SHA-256
`081e4de4be8e38fac6ed4d95e3b1a0b9f6d31c090ddc36e1696b349fe406f575`.
Other installed Codex bin directories exist, but none was executed or
requalified. The same bounded fake-only ladder, with only those two named
real-binary checks excluded, passed 347 tests and 26 subtests; 2 deselected.
The raw two failures remain visible and are not counted as passing.

Codex's durable registry does not expose a trustworthy terminal completion
timestamp in the returned record. This slice deliberately returns a
candidate, not a `DelegationResult`, and does not invent a completion time.
The next non-live Codex slice must persist a trusted terminal observation
time or prove an equivalent durable source before originator delivery.
The missing executable also requires a separate exact successor-binary
qualification before any real Codex invocation.

`CODEX_TERMINAL_REVERIFICATION=PASS_FAKE_ONLY`
`CODEX_PINNED_BINARY_PRESENT=NO`
`CODEX_TERMINAL_TIME_BOUND=NO`
`LIVE_CODEX_INVOCATION_AUTHORIZED=NO`
`PRODUCTION_READY=NO`
