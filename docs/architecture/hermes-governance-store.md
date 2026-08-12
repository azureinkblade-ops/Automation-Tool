# Hermes Phase 6E — Governance Store & SQLite Persistence

**Milestone:** Phase 6E (Ledger + State Integration + SQLite Governance Persistence)
**Parent plan:** `HERMES_PHASE6_DETERMINISTIC_CONSENSUS_PLAN.md`
**Predecessors:** 6A `1d65dc1`, 6B `8ded002`, 6C `3893317`, 6D `9b9b242`
**Status:** Implementation complete; commit held (branch `integrate/hermes-core` isolated through 6F).

## Goal

Persist the verified deterministic governance artifacts (6A/6B/6C/6D) into an
authoritative local store, detect tampering, re-verify hashes on load, and
advance task state only through valid governance transitions — without letting
persistence weaken any governance boundary.

## Architecture

```text
6A/6B/6C/6D deterministic domain logic   (SQL-free, unchanged)
            ↓
GovernanceStore                          (persistence abstraction)
            ↓
SQLiteGovernanceStore                    (single-file SQLite adapter)
            ↓
SQLite authoritative governance database (WAL-off / rollback journal)
```

### Rules (hard constraints)

- Deterministic governance logic remains **SQL-free**. SQLite lives only behind
  the `GovernanceStore` adapter; no SQL types or row ids enter deterministic
  identity.
- The SQLite database is the **record of truth**. `.json` files and Obsidian are
  not governance state. Anytype is a later operational projection.
- Acceptance **grants no execution authority** (`can_authorize_execution`
  const `false`, `requires_separate_authorization` const `true`).

## Components

### `governance_store.py`

- `GovernanceStore` — the persistence abstraction. Methods:
  `record_finding_set`, `record_consensus_evaluation`,
  `record_consensus_disposition`, `record_acceptance`,
  `record_evidence_record`, `record_review_documents`,
  `append_governance_event`, `load_task_governance_chain`, `verify_integrity`,
  `current_state`, `record_transition`.
- `GovernanceEvent` — append-only ledger entry (sequence_no, task_id,
  event_type, subject_sha256, previous_event_hash, event_hash, created_at).
- `GovernanceChain` — read-back bundle (finding_set, evaluation, disposition,
  acceptance, governance_state, events).
- `IntegrityReport` — `{ok, checked, failures}`.
- Error hierarchy: `GovernanceStoreError(RuntimeError)` →
  `GovernanceIntegrityError`, `GovernanceConflictError`,
  `GovernanceTransitionError`, `GovernanceSchemaError`, `GovernanceSqliteError`.

### `sqlite_governance_store.py`

- `SQLiteGovernanceStore` — implements `GovernanceStore`.
- **Schema** (normalized, versioned): `governance_schema_version`,
  `governance_tasks`, `evidence_packages`, `normalized_finding_sets`,
  `normalized_findings`, `consensus_evaluations`, `consensus_dispositions`,
  `acceptance_artifacts`, `acceptance_authority`, `governance_evidence`,
  `governance_reviews`, `governance_events`, `governance_state`.
- **Versioning:** `governance_schema_version` holds exactly one row. Bootstrap
  inserts `version=1` only when no row exists (`INSERT ... SELECT ... WHERE NOT
  EXISTS`), so a corrupted/incompatible version is detected and fails closed.
- **Journal mode:** rollback journal (`journal_mode = DELETE`), not WAL. The
  store is single-writer-per-process; DELETE mode guarantees a reopened
  connection observes all committed writes (WAL leaves a `-wal` file that can
  read as stale state on reopen).
- **Idempotency:** identical records (same identity hash, same content) are
  no-ops. Conflicting duplicates (same identity, different content) raise
  `GovernanceConflictError` and fail closed.
- **Hash re-verification:** every artifact stored keeps its canonical document
  JSON. On load, the stored document is reconstructed into the domain object and
  its canonical hash is re-derived and compared to the stored sha256. Any
  mismatch (tamper) raises `GovernanceIntegrityError`.
- **Ledger:** `governance_events` is append-only and hash-linked. Each event
  hash = `sha256(canonical_json({sequence_no, task_id, event_type,
  subject_sha256, previous_event_hash, created_at}))`; `previous_event_hash`
  chains to the prior event. `verify_integrity()` replays the chain and detects
  hash mismatch, chain break, sequence gap, or duplicate sequence. It is
  read-only and never repairs.

### State integration

`record_transition(task_id, from_state, to_state)` enforces the
**governance-scoped** transition rules (plan section 12/14):

- permitted edges: `UNDER_REVIEW → CONSENSUS_CALCULATED → ACCEPTED`;
- requires a persisted disposition **and** acceptance (complete upstream chain);
- only an `ACCEPTED` disposition may advance to `ACCEPTED`;
- task/evidence binding: every persisted artifact must carry the same `task_id`;
- acceptance authority must be `can_authorize_execution = false` and
  `requires_separate_authorization = true`;
- persisted hashes were already re-verified by `load_task_governance_chain`, so
  a tampered record is caught before the transition runs.
- On success, the governance state row is updated and a
  `governance.transition.recorded` event is appended, atomically.

**Note on the application state machine.** The existing `state_machine`
(`tools/hermes_core/state_machine.py`) validates a full `hermes.task` envelope
(including `scope.project_id`, `permitted_*_paths`, `network_policy`) and a
`hermes.consensus` envelope that 6E does not own or fabricate. Reusing its
`validate_transition` would require synthesizing application execution scope,
which would violate the no-fabrication governance discipline. 6E therefore
enforces the governance subset against persisted artifacts and records the
transition in its own SQLite ledger. The application-level `validate_transition`
remains the full-lifecycle gate for complete task envelopes; the JSONL
`EventLedger` / `TransitionRecorder` remain the application's transition chain
and are not duplicated.

## Verification

- 30 new 6E tests across `test_governance_store`, `test_governance_ledger`,
  `test_governance_state_integration`.
- Full Hermes core suite: **234 tests pass** (204 baseline + 30).
- Mutation testing: 4 governance-rule mutants each cause ≥1 targeted test
  failure (disposition gate, authority gate, schema-version check, ledger
  previous-hash verification). Source restored byte-exactly.
- Ad-hoc SQLite proof: bootstrap, persist full 6A→6D accepted chain, read back
  (acceptance sha `27d6d92f…` matches 6D fixture), idempotent re-record,
  tamper detection, valid transition to `ACCEPTED`, ledger verification,
  authority boundary, close/reopen. All temporary databases removed.

## Out of scope

Execution authorization, worker/model invocation, Kilo/Codex/Copilot integration,
Ollama routing, browser automation, publishing, Open Design/Anytype projection,
Obsidian authoritative machine state, paid API fallback, merge to `main`.
