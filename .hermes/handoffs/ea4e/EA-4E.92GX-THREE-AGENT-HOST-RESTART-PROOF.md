# EA-4E.92GX Three-Agent Host Restart Proof

Status: NON-LIVE TEST CHECKPOINT. Parent: EA-4E.92GW.

The explicit, default-disabled `AgentPingRecoveryHost` previously had a
focused host test only for Codex. The store-only entrypoint had lower-level
coverage for Codex, Kilo, and OpenCode, but that did not prove the one host
API selected and replayed all three receivers after a store reopen.

A parametrized fake-only test now persists the appropriate terminal witness
for each agent, closes and reopens the execution-start store, invokes the
same explicitly enabled host, and verifies one successful result, one
originator mailbox message, and exact replay. No receiver or model is
launched. The bounded eight-file cross-agent/start/result ladder passed
68 tests with zero failures; `git diff --check` passed.

This closes a host-level test gap, not the production wiring gap. There is
still no `app.py` call site, trusted Kilo/OpenCode process-to-capture owner,
qualified Codex successor binary, or separately authorized real handoff.
`LIVE_AGENT_HANDOFF=NOT_QUALIFIED`; `PRODUCTION_READY=NO`.
