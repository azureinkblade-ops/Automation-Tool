# EA-4E.92FY Exact Agent Start Binding

Status: NON-LIVE PURE START BINDING / DURABLE HOST HOLD
Baseline: `5092783a0d992ed235ba375fa305a81b3898a49c`
Date: 2026-10-09 (America/Phoenix)

`bind_agent_start_result()` accepts only a hash-consistent `STARTED`
artifact. It binds the deterministic start-result ID, launch and reservation
hashes, route, task, named worker, runtime binding, one-send idempotency key,
runtime-run ID, and a 64-character runtime-evidence hash to the already bound
Codex/Kilo/OpenCode invocation. Missing, UNKNOWN, FAILED, divergent, or
tampered start artifacts fail closed.

The function is pure. A caller-supplied artifact is not durable proof; the
future production host must read the artifact from the qualified
`SQLiteExecutionStartStore` and reconcile uncertain starts without sending
again. This slice does not verify lease expiry at result emission, resolve
cross-store recovery, invoke a receiver/model, or publish a result.

Focused fake-only tests and adjacent start/delegation regression suites
passed 184 tests and 26 subtests with zero failures. No network, Docker,
receiver, GPU, ComfyUI, or production activation was used.

`THREE_AGENT_EXACT_START_BINDING=PASS_FAKE_ONLY`
`DURABLE_START_PROVENANCE=NOT_WIRED`
`CROSS_STORE_RECOVERY_CONTRACT=NOT_FROZEN`
`PRODUCTION_READY=NO`
