# EA-4E.92FR Terminal Agent Candidate Binding

Status: NON-LIVE SYNTHETIC TRANSPORT BINDING / VERIFIED RESULT HOLD
Baseline: `53e2e6265e4ad7bddd188f0e442f3cabea79cb94`
Date: 2026-10-09 (America/Phoenix)

`bind_terminal_agent_candidate()` checks one synthetic Kilo/OpenCode
`ExecutionOutcome` against a `BoundAgentInvocation`. The process-start flag,
non-replay state, positive PID, receiver-specific terminal state, exact
idempotency key, and runtime-run ID must agree before terminal text is decoded
as a structural candidate. Failed, replayed, absent, or divergent outcomes
are denied. Codex uses its separate structured-result adapter contract.

This function is pure. The tests construct fake outcomes; they do not call an
adapter, start a process, use a network, mutate Docker, or write any result
store. The bounded predecessor gate passed 295 tests and 29 subtests. The
output is still only `AgentResultCandidate`: no schema instance, output file,
evidence hash, cancellation/revocation state, or actual adapter provenance
has been verified, and no durable result is recorded.

Before live integration, the host must use durable artifacts and a qualified
receiver under an exact bounded authority. It must also independently
validate the candidate against the delegated schema and actual outputs, then
write the canonical result and originator message atomically. Current direct
Kilo/OpenCode qualification layers still fabricate random IDs and cannot be
substituted for this path. The local-container gateway/control and the
separate live/activation gates remain HOLD.

`FAKE_TERMINAL_IDENTITY_BINDING=PASS`
`VERIFIED_DELEGATION_RESULT=NO`
`LIVE_KILO_OR_OPENCODE_HANDOFF=NO`
`PRODUCTION_READY=NO`
