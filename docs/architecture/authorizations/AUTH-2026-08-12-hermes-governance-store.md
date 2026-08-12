---
title: "AUTH-2026-08-12 Hermes Governance Store"
document_id: "AUTH-2026-08-12-HERMES-GOVERNANCE-STORE"
version: "0.1.0"
status: "proposed"
owner: "David Powell"
system: "Hermes"
last_updated: "2026-08-12"
---

# AUTH-2026-08-12 Hermes Governance Store

This authorization permits a tightly scoped SQLite governance persistence and
state-integration layer as Phase 6 milestone 6E.

## Authorized scope

1. Add a `GovernanceStore` persistence abstraction under `tools/hermes_core/**`.
2. Add a `SQLiteGovernanceStore` implementing it against a single-file SQLite
   database, including a versioned, normalized schema and bootstrap.
3. Persist the verified 6A/6B/6C/6D domain artifacts plus the frozen evidence
   record and review documents as the immutable governance inputs.
4. Implement an append-only, hash-linked `governance_events` ledger and an
   integrity verifier that detects hash mismatch, chain break, sequence gap, and
   duplicate sequence (read-only, never auto-repairs).
5. Re-verify every persisted artifact's canonical hash on load; raise
   `GovernanceIntegrityError` on any mismatch (tamper detection).
6. Enforce idempotent re-records and conflict-fail-closed semantics for
   identical-identity/different-content writes.
7. Advance task governance state only through the permitted edges
   (`UNDER_REVIEW → CONSENSUS_CALCULATED → ACCEPTED`) and only when the full
   upstream chain is present with an `ACCEPTED` disposition and a
   non-execution-authorizing acceptance.
8. Add focused unit tests under `tests/hermes_core/**` and document the contract
   under `docs/architecture/**`, including a mutation-testing pass and an ad-hoc
   SQLite proof.

## Explicit prohibitions

- No execution authorization and no governance-authority grant. Acceptance is
  explicitly distinct from execution permission (ADR-0004); `can_authorize_
  execution` stays `false` and `requires_separate_authorization` stays `true`.
- No model invocation, no worker routing, no Ollama/model execution, no browser
  automation, no publishing.
- No `.json` file written as the governance record of truth; SQLite is the
  authoritative store and canonical serialization is an internal hashing
  mechanism only.
- No Obsidian authoritative machine state; Obsidian remains human-readable
  architecture/knowledge only.
- No Anytype projection; that is a later operational step.
- No silent replacement of governance truth; conflicting duplicates fail closed.
- No implicit destructive migration; the schema version fails closed on mismatch.
- No merge to `main`; the `integrate/hermes-core` branch stays isolated through
  6F.

## Recorded dependencies

- 6A `1d65dc1`, 6B `8ded002`, 6C `3893317`, 6D `9b9b242` produce the artifacts
  persisted here.
- ADR-0003/ADR-0004 define acceptance eligibility and separate execution
  authorization; this store preserves those boundaries.
- The application-level `state_machine.validate_transition` remains the
  full-lifecycle gate for complete task envelopes; 6E enforces the governance
  subset against persisted artifacts and records transitions in its own SQLite
  ledger (it does not fabricate `hermes.task`/`hermes.consensus` application
  envelopes).
- 6E architectural decision: SQLite authoritative store; deterministic domain
  logic (6A-6D) stays SQL-free behind `GovernanceStore`.
