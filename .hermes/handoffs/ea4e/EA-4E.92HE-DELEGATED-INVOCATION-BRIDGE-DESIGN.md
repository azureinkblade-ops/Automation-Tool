# EA-4E.92HE Delegated Invocation Bridge Design

Status: NON-LIVE SOURCE DESIGN. Parent: EA-4E.92HD.

## Source finding

The accepted delegation's `attempt_id`, `launch_attempt_id`, idempotency key,
and runtime run ID are bound by `agent_receiver_lineage.py` and reloaded by
`agent_start_witness.py`. The generic EA-4D STARTED artifact proves a worker
start, not the later Kilo/OpenCode receiver process.

`ProductionInvocationAuthorization` is bound to an
`execution_request_id`, receiver, EA-4E executor `binding_id`, and enablement.
Its issuer and policy do not bind that request ID to the EA-4D accepted
attempt. The EA-4D `WorkerRuntimeBinding` is symbolic worker metadata;
its `runtime_binding_id`/hash are not the EA-4E executor `binding_id`.
Equality between those IDs cannot be assumed or manufactured.

The current `RealKiloProductionExecutor` and
`RealOpenCodeProductionExecutor` generate new UUID-based invocation,
launch, and delegation IDs and retain the adapter outcome only in memory.
Calling either for an accepted delegated task would sever lineage.
`SQLiteAgentTerminalCaptureStore.capture` accepts a supplied
`ExecutionOutcome` as data; that dataclass does not attest process ownership.

## Required non-live bridge

1. Derive one versioned `execution_request_id` from the durable accepted
   attempt, exact receipt hash, launch hash, and STARTED hash. Persist the
   relation before any issuance. Neither a caller-selected request ID nor a
   new UUID is valid.
2. Resolve an exact EA-4E executor binding and separately validate the
   EA-4D worker binding against the launch. Record both binding identities
   and hashes in one immutable cross-domain artifact. Do not compare the IDs
   as strings or infer one from the other. Receiver, transport, binary/model
   pin, credential scope, and expiry must be checked independently.
3. Issue and consume a durable, request-scoped invocation authorization for
   that exact derived request ID. Its claim and the EA-4D receiver-start
   fence are different one-shot stores. No cross-store atomicity is assumed:
   after either durable claim, any crash yields UNKNOWN/reconciliation, never
   an automatic second process start.
4. A new trusted process owner must call the adapter with the accepted
   idempotency key, launch ID, delegation ID, and runtime run ID, observe the
   actual PID/argv/terminal bytes, check cancellation and accounting, and
   commit terminal capture before result return. The old live executors are
   not this owner. A caller-provided `ExecutionOutcome` is insufficient.
5. Keep the result host observational/recovery-only. An internal explicit
   trigger may be added only after the trusted owner and negative tests pass;
   it must not be wired to startup, a generic route, or scheduled scanning.

## Qualification boundary

The first implementation slice adds a pure, non-executing
`AgentInvocationBridge` and builder. It derives a deterministic request ID
from the accepted attempt and exact receipt/launch/STARTED hashes, records
both distinct binding domains, and rejects mismatched resolution, registry,
receiver, or expired binding inputs against a supplied timezone-aware current
time. Focused fake-only tests: 6 passed.
The staged 92HE/92HD/92HC/capture/recovery/start ladder passed 65 tests,
0 failed, with one inherited `app.py` invalid-escape warning.
This value is not yet persisted; it cannot authorize invocation.

Next slices: persist the bridge before issuance with replay/conflict and
cancellation checks; validate current binding and authorization at claim time;
then separately implement process ownership and durable terminal proof. No
real receiver/model call, production
activation, Docker mutation, GPU, or ComfyUI operation is authorized by this
design. `PRODUCTION_READY=NO`.
