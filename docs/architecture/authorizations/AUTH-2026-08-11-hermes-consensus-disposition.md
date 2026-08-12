---
title: "AUTH-2026-08-11 Hermes Consensus Disposition"
document_id: "AUTH-2026-08-11-HERMES-CONSENSUS-DISPOSITION"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# AUTH-2026-08-11 Hermes Consensus Disposition

This authorization permits a tightly scoped terminal consensus disposition implementation as Phase 6 milestone 6C.

## Authorized scope

1. Add a local, deterministic consensus disposition mapper under `tools/hermes_core/**`.
2. Add a focused unit test file under `tests/hermes_core/**`.
3. Document the consensus disposition contract under `docs/architecture/**`, including the canonical disposition vocabulary and the policy decisions made during implementation.
4. Export the new types from the `tools/hermes_core` package and list the new document in the architecture index.
5. Accept a valid Phase 6B `ConsensusEvaluation` plus the matching `NormalizedFindingSet` as the only inputs.
6. Map the four 6B agreement classes to the canonical terminal dispositions (`ACCEPTED`, `REJECTED`, `ESCALATED`, `BLOCKED`, `INCONCLUSIVE`) under ADR-0003's frozen policy.
7. Enforce the documented critical/high blocking rule exactly as ADR-0003 states, and apply no blocking rule that the repository does not authorize.
8. Emit a deterministic disposition hash so later milestones (6D/6E) can bind to and verify the exact terminal disposition.

## Explicit prohibitions

- No `app.py` changes.
- No posting workflow changes.
- No browser automation.
- No external services.
- No new persisted schema file. The disposition result stays an internal deterministic object in this milestone; if a persisted `hermes.consensus` artifact is ever required, that is 6D.
- No ledger append, no state transition, no acceptance artifact generation.
- No execution authorization and no governance-authority grant. Acceptance disposition is explicitly distinct from execution permission (state-machine: `ACCEPTED` -> `AWAITING_EXECUTION_AUTHORIZATION`).
- No reviewer adjudication and no model arbitration. The disposition never decides which reviewer is correct; `material_disagreement` maps to `ESCALATED` without choosing a winner.
- No invented quorum. `expected_review_count` is only checked for consistency with the 6B evaluation; no value is assumed.
- No invented numeric confidence threshold. Confidence is preserved for auditability only; `review-model.md` section 8's threshold requirement is recorded as a deferred dependency.
- No silent conversion of `inconclusive` or `escalate` recommendations into accept/reject.
- No authority to modify state, authorize execution, or execute reviewer models.

## Recorded dependencies

- ADR-0003 requires "no unresolved critical findings" and "no unresolved high findings" for acceptance. The blocking set is therefore exactly {critical, high}. Medium/low/info findings are not enumerated as blocking in ADR-0003, so by the non-invention rule they do not block; their disposition follows the unanimous recommendation mapping and is recorded as `lower_severity_policy_resolved`.
- `review-model.md` section 8 requires per-reviewer confidence above a threshold; no numeric threshold exists anywhere in the repository. Confidence gating remains unimplemented at 6C and is recorded as a governance dependency (`confidence_threshold_not_defined`) rather than resolved by invention.
- `review-model.md` section 6 recommendation names (`ACCEPTABLE`/`ESCALATE`/`BLOCK`/`INCONCLUSIVE`) diverge from the implemented `review.schema.yaml` enum (`accept`/`reject`/`inconclusive`/`escalate`). The implemented schema is authoritative for code; the prose reconciliation is out of scope here.
