# EA-4E.92FZ Durable Agent Start Witness

Status: NON-LIVE READ-ONLY CROSS-STORE WITNESS / RESULT HOST HOLD
Baseline: `8178dbf2b1fc9a9fde0315cd153554ef90865ae7`
Date: 2026-10-09 (America/Phoenix)

`load_bound_agent_start()` reads an accepted receipt, task, and capability
lease from `SQLiteDelegationStore`, then reads the start result and launch
attempt from `SQLiteExecutionStartStore`. The exact 92FY binder checks the
durable STARTED result against the launch, one-send key, receiver, and runtime
identity. The witness is read-only and performs no dispatch or result write.

Isolated real-SQLite tests cover Codex, Kilo, and OpenCode with a reopened
start database. Missing, UNKNOWN, FAILED, wrong-runtime, and missing-launch
records are denied. The bounded fake-only start/delegation ladder passed 201
tests and 26 subtests with zero failures.

This witness does not recheck cancellation, revocation, or trusted lease
expiry at terminal emission; it does not establish a cross-database atomic
snapshot. It also does not verify the adapter's terminal output or publish a
result. A production host must make those decisions under a separately
frozen recovery contract. No receiver, model, network, Docker, GPU, ComfyUI,
or production activation was invoked.

`THREE_AGENT_DURABLE_START_WITNESS=PASS_FAKE_ONLY`
`CROSS_STORE_TERMINAL_RECHECK=NOT_WIRED`
`LIVE_THREE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
