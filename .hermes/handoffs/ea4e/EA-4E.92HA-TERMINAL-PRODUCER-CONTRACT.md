# EA-4E.92HA Delegated Terminal Producer Contract

Status: NON-LIVE SOURCE REVIEW / DESIGN. Parent: EA-4E.92GZ.

## Source finding

`AgentPingRecoveryHost` can recover a result only after Codex registry terminal
evidence or a Kilo/OpenCode row in `agent_terminal_captures`. The latter has no
production writer. The historical `RealKiloProductionExecutor` and
`RealOpenCodeProductionExecutor` generate new UUID-based idempotency, launch,
and delegation IDs, keep `last_outcome` only in memory, and do not write that
row. Their outcomes are not accepted-delegation evidence.

`LocalWorkerRuntimeAdapter` records a generic worker/probe STARTED event in
its idempotency registry. Kilo/OpenCode adapters launch their receiver processes
inside `execute`. The worker STARTED event alone does not attest to the later
receiver PID, terminal bytes, or result. A second adapter call after replay is
not recovery; it can create duplicate work.

## Required owner

1. Consume one already accepted attempt and its immutable receipt, lease,
   launch, runtime binding, and durable STARTED witness. Do not generate new
   identities or infer authority from the result host's `enabled` switch.
2. Bind the receiver invocation to the exact launch idempotency key,
   `launch_attempt_id`, `delegation_id`, and receiver-specific
   `runtime_run_id` from that witness. Establish which process or worker owns
   the actual receiver PID. Keep the generic worker STARTED event distinct
   from receiver process start and terminal observation.
3. Admit at most one receiver process under a separately qualified,
   request-scoped invocation authorization and exact runtime/model/binary
   binding. On restart or uncertain start, reconcile durable evidence;
   never call the adapter again merely to obtain an outcome.
4. Verify the observed process identity, argv/runtime binding, terminal
   state, output bytes, cancellation, and invocation accounting. Treat a
   supplied `ExecutionOutcome` dataclass as data, not proof that a process
   ran. A terminal success candidate must be strict JSON and instance-bound.
5. Persist the terminal candidate under the accepted attempt through
   `SQLiteAgentTerminalCaptureStore.capture` before result return. A failed
   or ambiguous capture write leaves the delegated result UNKNOWN. Exact
   replay must preserve one capture, one result, and one originator message;
   conflicting terminal evidence must deny.
6. Expose an explicit internal trigger with requester authorization and a
   bounded attempt ID. Do not attach it to startup, a generic route, or a
   scheduled scan. The result host remains read/recovery-only and must not
   launch a process.

## Qualification and stop conditions

Fake-only tests must cover both receivers, wrong accepted identities, worker
STARTED without receiver terminal, crash before capture, crash after capture,
duplicate trigger, divergent outcome, expiry/cancellation, and restart replay.
Actual process and model qualification, credentials, provider data-use policy,
binary/transport pins, and the local-container provenance profile are separate
gates. No old commit-bound authorization may be reused for new source.

This packet is not a live-call authorization or a claim of process provenance.
No receiver, model, Docker, GPU, or ComfyUI operation was run.
`PRODUCTION_READY=NO`.
