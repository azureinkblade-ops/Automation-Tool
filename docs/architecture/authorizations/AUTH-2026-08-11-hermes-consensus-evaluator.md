---
title: "AUTH-2026-08-11 Hermes Consensus Evaluator"
document_id: "AUTH-2026-08-11-HERMES-CONSENSUS-EVALUATOR"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-11"
---

# AUTH-2026-08-11 Hermes Consensus Evaluator

This authorization permits a tightly scoped agreement/disagreement evaluator implementation as Phase 6 milestone 6B.

## Authorized scope

1. Add a local, deterministic consensus evaluator under `tools/hermes_core/**`.
2. Add a focused unit test file under `tests/hermes_core/**`.
3. Document the consensus evaluator contract under `docs/architecture/**`, including the agreement-class vocabulary introduced by this milestone.
4. Export the new types from the `tools/hermes_core` package and list the new document in the architecture index.
5. Require a normalized finding set plus validated review reports bound to a single frozen evidence package as the only accepted input.
6. Accept an expected review count supplied from existing policy or assignment data, without inventing a quorum.
7. Emit a deterministic evaluation hash so later milestones can bind to and verify the exact consensus decision.

## Explicit prohibitions

- No `app.py` changes.
- No posting workflow changes.
- No browser automation.
- No external services.
- No new schema file. The evaluation result stays an internal deterministic object in this milestone.
- No ledger append, no state transition, no acceptance artifact generation.
- No terminal disposition mapping. Producing `ACCEPTED`, `ESCALATED`, `BLOCKED`, or `INCONCLUSIVE` is milestone 6C.
- No reviewer adjudication and no model arbitration. The evaluator never decides which reviewer is correct.
- No invented quorum, confidence threshold, or majority policy. ADR-0003 defers majority voting until reviewer reliability is measured.
- No silent conversion of `inconclusive` or `escalate` recommendations into pass or fail.
- No authority to authorize execution, modify state, or execute reviewer models.

## Recorded dependencies

- ADR-0003 requires no unresolved critical/high findings for acceptance, and `review-model.md` section 8 requires per-reviewer confidence above a threshold. No numeric threshold exists in the repository. Both remain unimplemented at 6B and are recorded as governance dependencies for 6C rather than resolved by invention.
- `review-model.md` section 6 recommendation names diverge from the implemented `review.schema.yaml` enum. The implemented schema is authoritative for code; the prose reconciliation is out of scope here.
