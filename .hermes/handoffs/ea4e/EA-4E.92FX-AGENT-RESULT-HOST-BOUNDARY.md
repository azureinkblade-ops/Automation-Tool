# EA-4E.92FX Agent Result Host Boundary

Status: NON-LIVE INTEGRATION REVIEW / PRODUCTION HOST NOT WIRED
Baseline: `c706abef6e9977a1510999c921fb193be0c42418`
Date: 2026-10-09 (America/Phoenix)

The source now has a strict candidate parser, a committed no-output ping
schema, a pure canonical ping-result builder, and an atomic SQLite
result/originator-mailbox writer. Fake-only tests exercise all three named
agents through the mailbox. No production app host currently calls that
chain for a real Codex, Kilo, or OpenCode result. The existing production
app host handles governed receiver dispatch; it is not the delegated-result
return host.

The next host must first bind the canonical task, lease, accepted receipt,
launch attempt, start result, adapter terminal record, and candidate to one
delegation/attempt/runtime identity. A `RECORDED` launch alone is not proof of
start. `SQLiteExecutionStartStore.get_execution_start_result()` can return
`STARTED`, `FAILED`, `UNKNOWN`, or no result; only a verified matching STARTED
artifact can proceed. UNKNOWN or absent start requires read-only recovery,
never a new send or a fabricated success. Kilo/OpenCode adapter terminal
text remains a candidate, not a verified result.

The authority/result database and execution-start database are separate.
The host must define a fail-closed ordering for start observation, lease
window and cancellation checks, candidate validation, and the final atomic
result/delivery write. The 92FV transaction guard denies a new success after
durable cancellation/revocation, but it does not prove trusted lease expiry,
start outcome, or arbitrary output bytes. The no-output ping schema is the
only currently implemented payload verifier. Caller-supplied schema IDs and
timestamps must not become trust assertions.

Required fake-only acceptance cases before host activation: exact lineage
and STARTED match; missing/UNKNOWN/FAILED or mismatched start; cancellation,
revocation, and expiry at the handoff boundary; forged candidate/evidence;
replay after crash without a second send; one result and one mailbox message;
originator claim/ACK after restart. Real receiver, Docker, network, model,
GPU, and production activation remain separately governed.

`FAKE_ONLY_THREE_AGENT_MAILBOX_PATH=PASS`
`PRODUCTION_RESULT_HOST_WIRED=NO`
`CROSS_STORE_RECOVERY_CONTRACT=NOT_FROZEN`
`LIVE_THREE_AGENT_CONNECTION=NO`
`PRODUCTION_READY=NO`
