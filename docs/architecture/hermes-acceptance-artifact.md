# Hermes Phase 6D — Acceptance Artifact Builder

**Status:** Implemented (2026-08-12)
**Milestone:** Phase 6D
**Depends on:** 6A (`1d65dc1`), 6B (`8ded002`), 6C (`3893317`)
**Persistence boundary:** authoritative store is SQLite at 6E; 6D is SQL-free (see [[Hermes Governance Store - SQLite Persistence Decision]]).
**Schema envelope:** validates against `hermes.acceptance` (`docs/architecture/schemas/acceptance.schema.yaml`).

## Purpose

Build an immutable acceptance artifact from a verified Phase 6C consensus
disposition, binding the full evidence chain into one deterministic record:

```text
task
  ↓
frozen evidence
  ↓
validated reviews
  ↓
normalized findings (6A)
  ↓
consensus evaluation (6B)
  ↓
terminal disposition (6C)
  ↓
acceptance artifact (6D)
```

6D is deterministic, evidence-bound, auditable, read-only with respect to
Hermes state, and non-authoritative with respect to execution. It performs no
persistence, mutates no task state, appends no ledger event, authorizes no
execution, invokes no model, adjudicates no reviewer, and introduces no
majority-vote rule.

## Implementation

`tools/hermes_core/acceptance_artifact.py`:

- `AcceptanceArtifact` — frozen dataclass; the immutable record.
- `AcceptanceArtifactBuilder` — `build(disposition, evaluation, finding_set)`.
- `AcceptanceArtifactError(ValueError)` — raised when acceptance cannot be
  built deterministically.

### Invariants enforced

- Input is a valid `ConsensusDisposition` (6C).
- All three upstream hashes are **re-derived**, not trusted:
  - `finding_set_sha256` re-verifies against `_finding_set_document`.
  - `evaluation_sha256` re-verifies against `_evaluation_document`.
  - `disposition_sha256` re-verifies against `_disposition_document`.
- Chain links are enforced:
  - `evaluation.finding_set_sha256 == finding_set.finding_set_sha256`
  - `disposition.finding_set_sha256 == finding_set.finding_set_sha256`
  - `disposition.evaluation_sha256 == evaluation.evaluation_sha256`
- Identity binding: `task_id` and `evidence_package_id` match across all three.
- Acceptance is generated **only** when
  `disposition == ACCEPTED` (the canonical acceptance-eligible terminal
  disposition from `consensus.schema.yaml` / ADR-0003 / ADR-0004). `BLOCKED`,
  `ESCALATED`, `REJECTED`, and `INCONCLUSIVE` cannot produce an acceptance
  artifact.
- `acceptance_sha256 = sha256_payload(_acceptance_document(artifact))`.
- The artifact `as_document()` validates against `hermes.acceptance`.
- No execution authority: `authority.can_authorize_execution = false`,
  `authority.requires_separate_authorization = true`.

### Hashing / identity policy

- Canonical serialization is an internal hashing mechanism only; no `.json`
  files are the record of truth (6E holds state).
- `accepted_at` is audit metadata and is **excluded** from the hashed shape
  (it is wall-clock time). It is included in `as_document()` for schema
  compliance. This keeps `acceptance_sha256` deterministic.
- Identity is derived in **two stages** (the `acceptance_id` is part of the
  final hashed document, so it cannot be derived from that same hash without
  circularity):
  - `acceptance_core_sha256 = sha256_payload(_acceptance_core(artifact))`
    where `_acceptance_core` is the canonical acceptance document **excluding**
    `acceptance_id`, `acceptance_sha256`, and `accepted_at`.
  - `acceptance_id = "acceptance-" + acceptance_core_sha256[:16]`.
  - `acceptance_sha256 = sha256_payload(_acceptance_document(artifact))`
    where `_acceptance_document` includes `acceptance_id` (deterministic once
    derived) but still excludes `accepted_at` and `acceptance_sha256`.
  Both digests are stable across runs; neither depends on runtime state.

## Canonical fixtures (independently re-derived)

Verified against `integrate/hermes-core` at commit `3893317` (6C); 6D builds
on top:

- 6C disposition hash: `106eb0d20d483d94e1a56f7209b5643ea153e281f560b5066b33ecf629deba8f`
- 6D acceptance hash (ACCEPTED, empty-finding fixture):
  `27d6d92feb5b87439375c6df2543dd36b469a2305a0eedbee24f284b408428fc`
- 6D acceptance id: `acceptance-b146144debbe6616`

## Out of scope (6E or later)

SQLite connection, SQL schema/migrations, `GovernanceStore` /
`SQLiteGovernanceStore`, ledger append, state transitions, execution
authorization, model invocation, majority voting, reviewer adjudication,
JSON-file persistence, Obsidian state, Anytype projection.

## Verification

- `tests/hermes_core/test_acceptance_artifact.py` — 31 tests (positive,
  non-eligible, tamper rejection, determinism, traceability, immutability,
  non-authority, side-effects, hash regression).
- Mutation-tested: seven governance-rule mutants each fail ≥1 test
  (eligibility for BLOCKED/ESCALATED; disposition/evaluation/finding-set hash
  re-verification; evidence-package binding; execution-authority block).
- Full Hermes core suite passes (173 prior + 31 new = 204).

See [[Hermes Phase 6 - Deterministic Consensus Plan]] and
[[Hermes Phase 6C - Consensus Disposition Plan]].
