# EA-4E.92GH Text Terminal Capture Store

Status: NON-LIVE STORE IMPLEMENTED / PRODUCTION ADAPTER HOST HOLD
Baseline: `f1d274ca4ffd783cf1071759e081d20a0744c130`
Date: 2026-10-09 (America/Phoenix)

`SQLiteAgentTerminalCaptureStore` adds an immutable attempt-keyed capture
to the delegation authority database for Kilo/OpenCode terminal text. A
trusted caller supplies an observed `ExecutionOutcome`; the store re-reads
the durable STARTED witness, validates the one-send/runtime/terminal
candidate, bounds raw text to 64 KiB, and records raw text, canonical
candidate, process metadata, and exact lineage under a checksum. Exact
capture replay returns the original; divergent capture conflicts. Missing
capture returns no candidate and must remain UNKNOWN rather than causing a
second send. Reads re-bind the current durable witness and deny inactive
authority or corrupted persisted bytes.

Fake-only tests use isolated real SQLite authority/start stores. Both text
receivers recover the same candidate after start-store reopening, without
another adapter call. Tests deny wrong send/terminal identity, divergent
text, corrupted storage, and cancellation after capture. The focused gate
passed 31 tests; the bounded cross-agent/start/result ladder passed 243
tests and 26 subtests, zero failures.

This store does not authenticate a real process on its own: the future
trusted adapter host must record the capture immediately after an observed
terminal return. A crash before that write remains uncertain. No production
app call path or real receiver was added. Generic output-byte verification,
trusted adapter-host wiring, and live qualification remain open.

`KILO_OPENCODE_CAPTURE_RESTART=PASS_FAKE_ONLY`
`TRUSTED_ADAPTER_HOST_WIRED=NO`
`LIVE_THREE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
