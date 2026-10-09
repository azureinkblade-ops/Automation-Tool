# EA-4E.92FT Instance-Bound Agent Ping Schema

Status: NON-LIVE PURE SCHEMA CHECK / DURABLE COMPLETION HOLD
Baseline: `0a53dd8873343449385c0eeb4540a87a7925c5dc`
Date: 2026-10-09 (America/Phoenix)

The first trusted result profile is intentionally no-output and limited to
`hermes.agent_ping_result/v1`. Its committed source material has a stable
SHA-256. `validate_agent_ping_candidate()` requires a canonical delegated
task, lease, accepted receipt, and candidate with identical lineage. It
checks the exact schema ID, version, SUCCEEDED outcome, empty output
manifest, receiver-specific ping statement, task-input hash, accepted-
receipt hash, and single receipt-derived evidence item. Malformed,
noncanonical, forged, wrong-schema, or divergent candidates fail closed.

This is a structural and instance-binding check for a qualification ping;
it is not general validation of file-producing tasks. The receipt hash is
read from the canonical accepted receipt, but this pure function does not
prove a real process ran. The Codex adapter has a separate structured output
path, while Kilo/OpenCode candidates pass the strict terminal-text decoder.
Synthetic tests for all three agents and negative cases ran with no receiver,
model, network, Docker, GPU, ComfyUI, or production activation. The bounded
fake-only ladder passed 308 tests and 29 subtests.

No code in this slice constructs `DelegationResult`, calls the result store,
or delivers to the originator. The next gates are observed output/evidence
verification for real workloads, durable cancellation/start/one-send recheck,
and a separate exact live authority for an actual Kilo/OpenCode handoff.

`NO_OUTPUT_PING_SCHEMA=PURE_QUALIFIED`
`GENERAL_RESULT_SCHEMA_REGISTRY=NO`
`LIVE_AGENT_TO_AGENT_RETURN=NO`
`PRODUCTION_READY=NO`
