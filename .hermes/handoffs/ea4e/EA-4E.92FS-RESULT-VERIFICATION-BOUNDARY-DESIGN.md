# EA-4E.92FS Result Verification Boundary Design

Status: NON-LIVE DESIGN / IMPLEMENTATION NOT QUALIFIED
Baseline: `fbbfe7ee36682269ea93d3f0ba34ced342e189f6`
Date: 2026-10-09 (America/Phoenix)

## Why 92FO-92FR do not complete the handoff

The new pure path binds task, lease, accepted receipt, launch, one-send key,
runtime-run ID, terminal transport record, and strict structured-text
candidate. It does not make candidate content true. In particular,
`SQLiteDelegationResultStore.record_verified_result_and_delivery()` receives
`validated_result_schema_id` from its caller. It compares that ID to the
delegation and lease, checks declared output paths against the lease, and
checks declared evidence entries against expected entries. It does not
validate the result payload against a schema registry, read output bytes,
hash output files, or establish that evidence was produced by the receiver.
Calling it directly with model-supplied text would therefore be unsound.

The existing Codex R12E-R8 proof is a bounded, instance-specific structured
output path, not a receiver-neutral production schema validator. Kilo and
OpenCode currently verify parseable terminal text, not the canonical result
body. Their direct qualification dispatchers fabricate delegation/launch IDs
and must not be used as the production return bridge.

## Required non-live implementation gates

1. Select a trusted, versioned schema by the delegated task's exact
   `expected_result_schema_id`; reject unknown IDs. The schema and its hash
   must come from committed/qualified authority, not receiver output or a
   mutable URL. Validate the candidate body, including outcome-specific
   error fields, against that schema. Bind instance constants such as task
   input hash and accepted-receipt hash where required.
2. Resolve each declared output under the lease's permitted paths and the
   approved workspace root. Deny path escape, reparse/symlink traversal,
   missing files, changing files, and content-hash mismatch. No model claim
   alone proves an output. The verifier must report exactly which bytes and
   hashes it observed.
3. Verify each evidence item from trusted runtime or output observations,
   not merely a matching self-reported manifest entry. Preserve immutable
   evidence provenance and bind it to the same delegation, attempt, launch,
   receiver, and runtime run.
4. Immediately before completion, recheck durable cancellation/revocation,
   lease window, start outcome, and one-send record. Distinguish a definite
   terminal failure from an uncertain start; never convert the latter to
   SUCCEEDED. Define recovery across separate authority/start stores before
   relying on a cross-store observation.
5. Only after 1-4 construct `DelegationResult` and invoke the existing
   atomic result/delivery write. On replay, return the same durable result
   and mailbox message without a second receiver send. Originator claim/ACK
   remains the final handoff step.

## Acceptance evidence for the next source slice

Use fake receiver output and isolated temporary stores. Cover malformed and
wrong-schema candidates, payload shape, mismatched lineage, output path
escape/reparse/hashing, missing or forged evidence, cancellation/revocation,
unknown start, replay/conflict, originator restart/ACK, and no write on any
denial. Do not use real Kilo/OpenCode, Docker mutation, a model, GPU, or
ComfyUI to qualify this source slice. A separate exact live authorization is
required later for the receiver/control-channel proof.

`STRUCTURAL_CANDIDATE_PATH=QUALIFIED_FAKE_ONLY`
`TRUSTED_SCHEMA_AND_EVIDENCE_VERIFIER=NOT_IMPLEMENTED`
`LIVE_AGENT_TO_AGENT_RETURN=HOLD`
`PRODUCTION_READY=NO`
