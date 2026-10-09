# EA-4E.92FQ Canonical Agent Launch Binding

Status: NON-LIVE PURE IDENTITY BINDING / EXECUTION HOLD
Baseline: `20c8f3ab21e58a5b114833010d6cf4cc87002e79`
Date: 2026-10-09 (America/Phoenix)

## Scope and proof

`bind_agent_invocation()` accepts an already canonical delegated task,
capability lease, ACCEPTED receiver receipt, and RECORDED
`ExecutionLaunchAttempt`. It verifies each artifact and the shared launch,
route, attempt, authorization, task, operation, input, and receiver identities.
It carries the durable launch idempotency key rather than fabricating a new
one. It checks the receipt's runtime run ID against the adapter-specific
derivation: Kilo uses the launch-attempt ID; Codex and OpenCode derive a
receiver-prefixed SHA-256 of the idempotency key. Divergent, tampered, or
empty-key launches fail closed.

The returned `BoundAgentInvocation` is an inert projection, not a launch
permit or a result-verification receipt. It does not query a live store,
claim an invocation, signal a gateway, call an adapter, or mark execution
complete. Synthetic tests cover all three receivers and negative lineage
cases. The bounded non-live launch/domain, delegation/result, Codex schema,
governed receiver, and send-claim ladder passed 284 tests and 29 subtests.

## Remaining integration boundary

Production must re-read the task, lease, receipt, and launch from their
authoritative durable stores immediately before use; a caller-supplied
projection cannot confer authority. The direct Kilo/OpenCode qualification
dispatchers still generate random IDs and are not this integration path.
The local gateway control channel, durable claim sequence, cancellation and
uncertain-start handling, actual output schema and evidence validation, and
originator result delivery remain separate gates. No real receiver or model
was invoked, and no Docker/GPU/ComfyUI mutation or activation occurred.

`CANONICAL_LAUNCH_IDENTITY=PURE_VERIFIED`
`LIVE_AGENT_HANDOFF=NO`
`DURABLE_RESULT_DELIVERY_FROM_REAL_RECEIVER=NO`
`PRODUCTION_READY=NO`
