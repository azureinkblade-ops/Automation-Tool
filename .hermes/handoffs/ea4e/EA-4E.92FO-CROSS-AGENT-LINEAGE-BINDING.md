# EA-4E.92FO Cross-Agent Lineage Binding

Status: NON-LIVE SOURCE + SYNTHETIC DELIVERY / LIVE RECEIVERS HOLD
Baseline: `14af3245eac3112484ef7674bad147f981a5ed59`
Date: 2026-10-09 (America/Phoenix)

## Connection trace

The R12A/B/E domain already supplies canonical delegated tasks, capability
leases, accepted receiver receipts, durable terminal results, result-delivery
mailbox messages, and originator acknowledgement. The R12E-R8 proof live-
qualified that end-to-end chain for Codex. EA-4E has Kilo and OpenCode
receiver adapters and an app production lifecycle, but the inspected app and
direct receiver host path do not call `SQLiteDelegationResultStore` or carry
the canonical delegation/attempt/receipt identities through the host result.
The EA-4E.9/.10 and .15/.16 qualification harnesses create fresh delegation
IDs inside their adapter calls. Those harnesses cannot serve as the return
path for an existing Hermes delegation.

## This slice

`tools/hermes_core/agent_receiver_lineage.py` verifies hash integrity and
identity equality across an already canonical task, lease, and ACCEPTED
receipt for `codex-cli-agent`, `kilo-cli-agent`, and `opencode-cli-agent`.
It returns only the bound lineage and expected result schema ID; it does not
issue authority, accept raw receiver text, launch, route, persist, or mark
completion. Callers must obtain the artifacts from durable Hermes state, not
from receiver-supplied claims.

`tests/hermes_core/test_ea4e92fo_agent_receiver_lineage.py` covers all three
agents, mismatched/tampered lineage, and a synthetic verified result returned
through the existing durable result store and originator mailbox after a
restart. A result that names OpenCode for a Kilo attempt is denied. The
synthetic result is built by the test; it is not adapter or model output.

The bounded lineage, delegation, result-delivery, Kilo/OpenCode governed,
and send-claim predecessor ladder passed 172 tests and 26 subtests. No real
receiver, model, network, Docker mutation, activation,
GPU, or ComfyUI activity occurred.

## Remaining production boundary

The next source design must bind one already-authorized receiver invocation
to these exact IDs without replacing them with random IDs, verify the actual
adapter result against the delegated schema/evidence contract, and only then
call `record_verified_result_and_delivery`. It must preserve one-send,
cancellation, failure/uncertain-start accounting and originator ACK. A public
host `execution_output` string is not a verified result. OpenCode's current
binary/config and missing raw capture, Kilo's current binary/model authority,
the local gateway control channel, and any real receiver run each retain
their separate gates. No production routing or activation is changed here.

`CANONICAL_CROSS_AGENT_LINEAGE=PURE_VERIFIED`
`SYNTHETIC_ORIGINATOR_RETURN=PASS`
`LIVE_KILO_RESULT_DELIVERY=NO`
`LIVE_OPENCODE_RESULT_DELIVERY=NO`
`PRODUCTION_READY=NO`
