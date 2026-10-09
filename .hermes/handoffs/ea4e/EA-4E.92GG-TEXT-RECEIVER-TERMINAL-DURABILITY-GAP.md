# EA-4E.92GG Text Receiver Terminal Durability Gap

Status: NON-LIVE SOURCE AUDIT / HOST RECOVERY HOLD
Baseline: `ff208fc7ad8938b040f0326bbf84f460d8cced05`
Date: 2026-10-09 (America/Phoenix)

The 92GE recovery contract requires the host to re-read durable terminal
evidence after a crash. The current adapters do not provide that uniformly.
`CodexInvocationRegistry` persists `result_json` and `_replay_verified()`
re-parses the recorded `CodexProcessResult`. Kilo's `execute()` and
OpenCode's `execute()` return `ExecutionOutcome` with an in-memory
`VerifiedResult`; their shown adapter paths do not persist the terminal
process result or parsed text. A repository search found no generic
delegated-agent terminal-capture store. The Regional Hand Repair evidence
store is a separate workload and is not a substitute for agent delegation.

Therefore a production host cannot yet recover a Kilo/OpenCode terminal
candidate after restart. It must not manufacture one from the durable
STARTED artifact, a model-text cache, or a replayed receiver invocation.
No app result-host wiring is authorized from the current source state.

The next non-live source slice should add one immutable, attempt-unique
terminal capture with the accepted delegation/attempt/launch/one-send/runtime
identities, receiver ID, exact process terminal classification, and bounded
raw terminal artifact (or its retained content-addressed bytes). It must be
written by the trusted adapter host immediately after an observed terminal
return and before result composition. Exact capture replay returns the
original bytes; divergent capture conflicts. Missing capture after crash
remains UNKNOWN and cannot trigger a second send or SUCCEEDED. Fake-only
tests must cover Kilo/OpenCode restart, duplicate capture, tamper, truncated
or absent raw output, and no result/mailbox write on uncertainty.

This finding does not change the local-Docker threat-model decision and
does not authorize any real receiver, model, Docker mutation, GPU, ComfyUI,
or production activation.

`CODEX_TERMINAL_PERSISTENCE=EXISTS`
`KILO_OPENCODE_TERMINAL_PERSISTENCE=MISSING`
`THREE_AGENT_CRASH_RECOVERY=HOLD`
`PRODUCTION_READY=NO`
