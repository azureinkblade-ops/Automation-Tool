---
title: "AUTH-2026-08-12 Hermes Acceptance Artifact"
document_id: "AUTH-2026-08-12-HERMES-ACCEPTANCE-ARTIFACT"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes Acceptance Artifact

This authorization permits a tightly scoped acceptance artifact builder as
Phase 6 milestone 6D.

## Authorized scope

1. Add a local, deterministic acceptance artifact builder under `tools/hermes_core/**`.
2. Add a focused unit test file under `tests/hermes_core/**`.
3. Document the acceptance artifact contract under `docs/architecture/**`, including the canonical evidence-chain binding and the policy decisions made during implementation.
4. Export the new types from the `tools/hermes_core` package and list the new document in the architecture index.
5. Accept a verified Phase 6C `ConsensusDisposition` plus the matching `ConsensusEvaluation` (6B) and `NormalizedFindingSet` (6A) as the only inputs.
6. Generate an acceptance artifact only when the disposition is `ACCEPTED` (the canonical acceptance-eligible terminal disposition from `consensus.schema.yaml` / ADR-0003 / ADR-0004).
7. Re-derive and verify every upstream hash (`finding_set_sha256`, `evaluation_sha256`, `disposition_sha256`) rather than trusting caller-supplied values, and enforce the finding-set→evaluation→disposition chain links and the shared `task_id` / `evidence_package_id` binding.
8. Emit a deterministic `acceptance_sha256` so 6E can persist and verify the exact acceptance record; the artifact `as_document()` validates against the existing `hermes.acceptance` schema.

## Explicit prohibitions

- No SQLite connection, SQL schema, migrations, or `GovernanceStore` / `SQLiteGovernanceStore` implementation. Persistence is 6E.
- No `.json` file written as the governance record of truth; canonical serialization is an internal hashing mechanism only.
- No ledger append, no state transition, no acceptance-driven mutation of Hermes state.
- No execution authorization and no governance-authority grant. Acceptance is explicitly distinct from execution permission (ADR-0004: separate artifacts, separate transitions).
- No model invocation, no reviewer adjudication, no model arbitration.
- No majority-vote rule and no invented quorum.
- No invented acceptance rule. Eligibility is exactly `disposition == ACCEPTED`; `BLOCKED`, `ESCALATED`, `REJECTED`, and `INCONCLUSIVE` cannot produce an acceptance artifact.
- No invented numeric confidence threshold.
- No authority to modify state, authorize execution, or execute reviewer models.

## Recorded dependencies

- ADR-0003 defines acceptance as the deterministic-consensus-satisfied outcome; only `ACCEPTED` is acceptance-eligible.
- ADR-0004 separates gate acceptance from execution authorization; this artifact grants no execution authority (`can_authorize_execution: false`, `requires_separate_authorization: true`).
- 6E architectural decision: SQLite is the authoritative governance store; deterministic domain logic (including 6D) remains SQL-free behind a `GovernanceStore` interface (see [[Hermes Governance Store - SQLite Persistence Decision]]).
- The `hermes.acceptance` schema requires `accepted_at` (audit metadata); it is excluded from the hashed identity so `acceptance_sha256` stays deterministic.
