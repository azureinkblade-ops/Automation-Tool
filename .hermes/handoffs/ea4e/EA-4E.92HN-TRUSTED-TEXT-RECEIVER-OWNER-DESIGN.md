# EA-4E.92HN Trusted Text Receiver Owner Design

Status: NON-LIVE SOURCE DESIGN / IMPLEMENTATION NOT AUTHORIZED BY THIS DOCUMENT.
Parents: EA-4E.92HA, 92HI, 92HM.

## Source constraints

- `AgentDelegatedClaimOwner.claim_and_fence` consumes the exact durable
  invocation authorization and commits a one-shot receiver-start fence. Its
  `FENCED` result is not evidence that a process ran.
- `RealKiloProductionExecutor` and `RealOpenCodeProductionExecutor` generate
  fresh UUID identities and retain the last adapter outcome in memory. They
  cannot execute an accepted delegated attempt or provide restart recovery.
- `KiloAdapter.execute` and `OpenCodeReceiverAdapter.execute` can return an
  `ExecutionOutcome`, but that dataclass can also be fabricated by a caller.
  `SQLiteAgentTerminalCaptureStore.capture` validates lineage and text; it
  does not independently attest the process, argv, or terminal bytes.
- The generic local-worker STARTED artifact precedes receiver execution.
  It must not be interpreted as the Kilo/OpenCode process-start event.

## Owner sequence

1. An explicit, authenticated internal request names one accepted attempt.
   Load its receipt, lease, launch, STARTED witness, reserved invocation
   bridge, exact executor binding, and current cancellation/revocation state.
   Reject any missing or changed identity. Never discover work by scanning.
2. Before irreversible claim, construct and validate the exact receiver
   command, model/transport pin, credential scope, expected output schema,
   bounded task bytes, and process-observation plan. Record a durable
   per-attempt process-owner intent keyed to the accepted attempt, not a new
   UUID. An existing intent or fence on a new request is reconcile-only.
3. Call the claim owner once. Only the same in-flight owner holding the
   successful `FENCED` result may attempt one receiver start. A crash or
   uncertain return at any point after the intent is UNKNOWN; restart must
   inspect, never call the adapter again merely to obtain an outcome.
4. A receiver-specific trusted process controller must own the process
   handle/ID and capture the actual argv, start event, bounded stdout/stderr
   or terminal event bytes, exit status, and cancellation outcome. The
   controller must expose immutable observation with a trusted owner identity
   and verify it against the prevalidated command/binding. A supplied
   `ExecutionOutcome`, PID number, or model text alone is not observation.
5. Convert only a verified, terminal observation into the receiver-specific
   outcome and strict structured result candidate. Persist terminal bytes or
   retained content-addressed bytes, process identity, and candidate under
   the accepted attempt before publishing any result. Extend the existing
   capture contract if necessary; do not claim that its current text-only
   row proves process provenance.
6. Return through the existing result/delivery store. On replay, read the
   committed capture and result; one attempt yields one result and one
   originator message. Divergent evidence denies. The result host stays
   read-only and must not launch or retry.

## Failure matrix

| Durable/observed point | Allowed recovery |
| --- | --- |
| Before process-owner intent | Revalidate from source and begin once. |
| Intent or authorization claim uncertain | UNKNOWN; no automatic reissue. |
| Fence committed, process start unobserved | RECEIVER_START_UNKNOWN; reconcile only. |
| Process observed alive, no terminal event | Inspect/contain the exact owned process; do not start another. |
| Terminal event observed, capture absent | Reconcile retained trusted bytes; do not rerun receiver. |
| Capture committed, result absent | Verify capture lineage and complete result/delivery once. |
| Result/delivery committed | Return existing durable result/message only. |

Cancellation committed before the fence denies start. Cancellation after the
fence is an in-flight cancellation requiring exact-process containment and
accounting; it must not be reported as proof that no invocation occurred.
Bounded live qualification must be separately authorized for an exact source
commit, receiver, binary/image and model, one task, credential/egress scope,
time window, output budget, and rollback/abort policy. No generic approval
or fake result substitutes for that authorization.

## Smallest next implementation

Add a default-disabled, non-live process-owner contract and durable intent,
with injected inert process observation. Qualify Kilo and OpenCode identity
binding, duplicate request, crash/reopen, cancellation timing, uncertain
start, terminal capture conflict, and exact replay. Do not wire `app.py`, a
scheduler, a generic route, or real adapters in that slice. The following
slice must implement a concrete trusted controller and prove process/byte
provenance in a separately governed environment before any live call.

`PRODUCTION_READY=NO`. No receiver, model, network, Docker, GPU, ComfyUI,
or production activation was invoked by this design.
