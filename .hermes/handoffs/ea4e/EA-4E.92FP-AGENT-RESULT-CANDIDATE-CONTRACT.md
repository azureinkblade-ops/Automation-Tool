# EA-4E.92FP Agent Result Candidate Contract

Status: NON-LIVE STRUCTURAL GATE / DURABLE COMPLETION HOLD
Baseline: `b121a8a2b7ba87f4d2a2c02c8ad3176edeabaf48`
Date: 2026-10-09 (America/Phoenix)

## Observed contract gap

Kilo and OpenCode adapters set `VerifiedResult.valid` when a successful
process yields a parseable terminal text event. Their parsed payload is
`{type, text, events}`, not a validated `DelegationResult`. The direct
qualification layers also generate new random delegation/launch IDs, so
those layers cannot represent an existing Hermes attempt. The app host
exposes `execution_output` as a public string; it is not a verified result.
The Codex R12E-R8 proof explicitly built a canonical result from structured
output after a governed launch. That proof does not qualify the Kilo or
OpenCode output paths.

## This slice

`agent_result_candidate.py` accepts only an already bound canonical lineage
and a valid adapter terminal-text result. It decodes exact-key, strict JSON
with the delegated schema ID, outcome, payload, manifests, and error fields.
Malformed text, duplicate keys, non-finite values, wrong schema, and missing
or extra fields are denied. The return type is intentionally named
`AgentResultCandidate`, not `DelegationResult` or verified evidence. No store
or production call site consumes it. Synthetic tests cover Codex, Kilo, and
OpenCode shapes; they never invoke an agent.
The bounded fake-only candidate, lineage, delegation/result, governed
receiver, and send-claim ladder passed 187 tests and 26 subtests.

## Remaining gates before a durable result

1. Bind the existing authorization, attempt, launch, idempotency key, and
   runtime run to one receiver invocation. Preserve durable one-send and
   cancellation/revocation semantics. The current direct qualification
   layers' random IDs cannot be used for this.
2. Validate the actual result payload against the delegated schema, not just
   the schema ID string. Verify every output reference, path scope, content
   hash, required evidence item, and receiver provenance before constructing
   `DelegationResult`.
3. Use the existing atomic result store and originator mailbox only after
   those validations. A failed or uncertain start must not be promoted to
   SUCCEEDED. Replays must return the same durable result without a new send.
4. Separately qualify current Kilo/OpenCode binary, transport, model, local
   gateway, and bounded live authority. This non-live decoder authorizes none
   of them. The strict mapped-byte route remains rejected; the revised local
   container profile remains incomplete and is not production-ready.

`STRUCTURED_CANDIDATE_DECODER=FAKE_ONLY`
`RESULT_SCHEMA_AND_EVIDENCE_VERIFIED=NO`
`LIVE_KILO_OR_OPENCODE_DELIVERY=NO`
`PRODUCTION_READY=NO`
