# EA-4E.92II Container Owner Integration Boundary

Status: SOURCE REVIEW / NON-LIVE / NO EXECUTION AUTHORITY.
Baseline: `12acec4a0485b25e21b0cd8d2d7d9589110428c8`.

The current governed chain has a durable task, bridge, invocation
authorization, claim intent, and one-shot receiver-start fence. The 92IB
Linux Kilo reservation is before that irreversible claim. The 92IG/92IH
checker can reject candidate metadata but cannot start a container.

`AgentTextProcessOwner` is not a Docker owner. It validates an
`AgentTextPingCommand`, invokes an injected `prepare/start/wait/kill`
controller, and records a host `pid` plus `argv_hash` in
`SQLiteAgentTextProcessObservationStore`. Its terminal record is bounded to
4 MiB stdout and 128 KiB stderr. It has no container ID, daemon network ID,
effective container-policy record, image/index binding, or gateway-peer
identity. Reinterpreting its PID/start fact as a Docker start would break
the recorded contract.

The narrow next implementation should be a separate, default-disabled
container owner and container-specific durable observation schema:

1. Bind the 92IB reservation and 92IE candidate hash to the accepted task,
   bridge, exact image/index, prepared bytes, and one attempt ID. Recheck
   lease/cancellation and preclaim state before any irreversible operation.
2. Compare a real daemon-observed created object with the candidate and a
   complete, separately qualified host policy: resource limits, dropped
   capabilities, namespace settings, tmpfs options, mount identity, and
   fresh network ID. The 92IG/92IH result alone is never a start permit.
3. Record the exact container ID and network/peer identity before claim.
   Consume the authorized invocation once, durably fence once, and then
   start only that ID. After fence, any ambiguous failure is UNKNOWN and
   reconciliation-only; never automatically create or start a replacement.
4. Contain on post-start report failure, retain bounded output/exit facts,
   verify gateway request/result lineage, and return a result to the
   originating agent only after the existing completion checks accept it.

The owner must have an inert injected fake controller in tests. A real
Docker controller or receiver probe requires a separate exact bounded live
authorization after non-live qualification; none is granted here. The
receiver must get only dummy local credentials for that probe. A real
provider/model and production activation are later, separately governed
boundaries. OpenCode requires its own runtime contract; Kilo qualification
does not transfer. The accepted local-container profile does not satisfy
strict 92AT mapped-byte proof, which remains HOLD.

Evidence: source review of `agent_delegated_claim_owner.py`,
`agent_text_process_owner.py`, `agent_text_process_observation.py`,
`agent_receiver_start_fence.py`, and 92IB/IE/IG/IH. No tests were changed,
no Docker/receiver/model was invoked, and no production state was altered.
