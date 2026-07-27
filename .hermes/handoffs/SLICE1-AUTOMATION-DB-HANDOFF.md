---
status: RECORDED
recorded: true
executed: false
handoff_id: SLICE1-AUTOMATION-DB-HANDOFF
revision: 2026-07-27
depends_on_proposal: SLICE1-OWNERSHIP-PROPOSAL
approved_by: David (repository owner)
approval_date: 2026-07-27
review_gate: "Proposal SLICE1-OWNERSHIP-PROPOSAL approved 2026-07-27; handoff now active for implementation"
tags: [handoff, automation-db, slice-1, studio-bible, retrieval]
---

# DRAFT Handoff - automation_db.py extension for Slice 1 AIVSB retrieval index

**handoff_id:** `SLICE1-AUTOMATION-DB-HANDOFF` · **revision:** 2026-07-27
**depends_on_proposal:** `SLICE1-OWNERSHIP-PROPOSAL`

## Prerequisite

This handoff MUST NOT be recorded or executed until the Source Ownership and
Ingestion Proposal (`SLICE1-OWNERSHIP-PROPOSAL`) is reviewed and approved by the
repository owner. Until then it is a dormant draft with no authority to change
`automation_db.py`. This dependency is recorded explicitly so future sessions and
audits do not mistake the draft for an active authorization.

## Status matrix

| Item | Status |
|---|---|
| External source architecture | Approved |
| Ingestion contract | Documented |
| automation_db.py handoff | Draft only |
| Shared-file authorization | Pending |
| Slice 1 scaffold | Blocked |

**THIS IS A DRAFT. It is NOT recorded as an active handoff and MUST NOT be executed
until the Slice 1 Source Ownership and Ingestion Proposal has been reviewed and
approved by the repository owner. Drafting this note is a preparation step only;
it does not authorize any change to `automation_db.py`.**

## Why the shared file is being touched

Slice 1 (Knowledge Retrieval Engine) requires a **derived, rebuildable** SQLite index
over the AIVSB YAML corpus. That index is persisted as two new tables inside the
existing automation database managed by `automation_db.py`. This is the only reason
`automation_db.py` is touched: to add the schema initialization for the derived
retrieval index. No other feature motivates this change.

## Explicit scope (allowed change)

- Additive `CREATE TABLE IF NOT EXISTS` migration(s) only, inside the existing
  schema-initialization path of `automation_db.py`.
- No modification of existing tables, columns, or rows.
- No change to existing connection, locking, or query behavior.
- No new public API beyond table creation (read/write happens in the isolated
  `scripts/aivsb/retrieval/index_store.py` package, not in `automation_db.py`).

## Exact tables introduced (schema finalized; from approved Slice 1 plan)

Two tables are added. Definitions are taken verbatim from the Slice 1 Implementation
Plan and are NOT open-ended:

```sql
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id      TEXT PRIMARY KEY,
    novel_id      TEXT NOT NULL,
    domain        TEXT NOT NULL,
    character_id  TEXT,
    platform      TEXT,
    asset_type    TEXT,
    status        TEXT NOT NULL,
    version       TEXT,
    content_hash  TEXT NOT NULL,
    summary       TEXT,
    body          TEXT NOT NULL,
    tags          TEXT,            -- JSON array
    source_file   TEXT NOT NULL,
    chunk_path    TEXT NOT NULL,   -- json-path within file
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id            TEXT PRIMARY KEY REFERENCES retrieval_chunks(chunk_id) ON DELETE CASCADE,
    embedding_model     TEXT NOT NULL,
    embedding_revision  TEXT,
    embedding_dim       INTEGER NOT NULL,
    embedded_at         TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    vector              BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rc_novel_domain ON retrieval_chunks(novel_id, domain);
CREATE INDEX IF NOT EXISTS idx_rc_char        ON retrieval_chunks(character_id);
CREATE INDEX IF NOT EXISTS idx_rc_platform     ON retrieval_chunks(platform);
CREATE INDEX IF NOT EXISTS idx_rc_status       ON retrieval_chunks(status);
CREATE INDEX IF NOT EXISTS idx_ce_model        ON chunk_embeddings(embedding_model);
```

No other tables, indexes, or columns are introduced by this handoff. Any additional
schema (e.g. a rerank-cache table) requires a separate, explicitly scoped handoff.

## Ownership boundary

- The change is limited to **database schema initialization** for AIVSB retrieval.
- `automation_db.py` must NOT contain: application logic, retrieval algorithms,
  ranking/rerank code, embedding/vector-generation code, or any `retrieve()` call site.
- All read/write of chunks and vectors lives in the isolated package
  `scripts/aivsb/retrieval/` (new, outside `app.py`, per AGENTS.md single-writer rule).
- `app.py` does not call any retrieval function in this slice (additive only).

## Rollback

- Removing the two new tables (`DROP TABLE IF EXISTS chunk_embeddings;
  DROP TABLE IF EXISTS retrieval_chunks;`) returns the database to its prior state.
- Because the tables are derived and rebuildable (regenerated from the external
  AIVSB source via `chunk_extractor`), dropping them loses no canonical data and
  does not affect any unrelated Automation Tool feature.

## Schema versioning convention (DECIDED, recorded)

- The migration is additive and idempotent (`CREATE TABLE IF NOT EXISTS`). It does
  **NOT** increment the shared `SCHEMA_VERSION` in `automation_db.py` (currently 6).
- **Decision (recorded):** `SCHEMA_VERSION` governs canonical feature tables. Additive
  `CREATE TABLE IF NOT EXISTS` for OPTIONAL DERIVED CACHES does not advance
  `SCHEMA_VERSION`. Rationale: `retrieval_chunks` / `chunk_embeddings` are rebuildable,
  carry no canonical data, and dropping them is non-destructive. A future migration reader
  must treat the handoff record (not the integer) as the authority for what schema "6"
  contains. This convention is also stated in-code at the migration site in `automation_db.py`.
- A future retrieval-schema change is a new additive migration with its own explicit handoff.

## Index rebuild policy (explicit)

- `retrieval_chunks` and `chunk_embeddings` are **derived caches**, not canonical data.
- They MAY be dropped and rebuilt at any time from the canonical AIVSB YAML corpus via
  `chunk_extractor` + `embed_worker`. Dropping them loses no canonical information and
  affects no unrelated feature.
- Maintainers treat the SQLite retrieval index as disposable and regenerable; the
  canonical source of truth is always the external AIVSB repository.

## Known gaps — provenance scope amendment (formally deferred, NOT satisfied)

- **Run-level provenance is DEFERRED, not satisfied.** The approved design required
  persisting, per indexing run: canonical AIVSB repository root, source Git commit,
  and extractor version. The current two-table schema captures per-chunk `version`
  (file hash), `content_hash`, embedding model/version, and `updated_at`, but has
  **no run-level field** for canonical repo root / source Git commit / extractor version.
- **Scope amendment (recorded):** this handoff is amended to defer run-level provenance
  to a **separate, separately-scoped schema lane**. Adding a `retrieval_index_runs` (or
  metadata) table would exceed the two-table scope of this handoff and therefore
  requires its own handoff + schema approval. That follow-up is NOT part of Slice 1.
- Until that lane lands, the index is reproducible only if the canonical source path and
  extractor version are supplied out-of-band (e.g. the deployment record that sets
  `AIVSB_SOURCE_PATH`, plus the recorded extractor version in `embed_worker.py`).
- **Accurate status:** Core Slice 1 retrieval implementation is complete and tested;
  the **full provenance acceptance criterion is deferred and unresolved**. This deferral
  is recorded deliberately so future readers do not mistake the absence for satisfaction.

## Dependencies (implementation remains contingent on)

1. Approved external-source architecture (AIVSB repository remains canonical owner;
   consumed via configurable `AIVSB_SOURCE_PATH`). See the Source Ownership Proposal.
2. `AIVSB_SOURCE_PATH` supplied as a deployment prerequisite (env/local config,
   validated at startup/index time, fails clearly when absent). No committed absolute
   path; no silent fallback to vault markdown, empty corpus, or repo-local copy.
3. MiniLM-first embedding decision (MiniLM shipping baseline; BGE-M3 parked pending
   separate evaluation). This overrides the plan's acceptance criterion #1.

## Out of scope (explicitly excluded from this handoff)

- Copying, symlinking, vendoring, or submoduling the AIVSB knowledge base into the
  Automation Tool repository.
- Modifying the AIVSB repository or its YAML corpus.
- Changing any existing retrieval behavior (none exists in this slice; `retrieve()` is
  new and lives in the isolated package, not here).
- Introducing BGE-M3 or any embedding-model download in this phase.
- Any change to `app.py` generation call sites.
- Any change to unrelated `automation_db.py` features (state snapshots, post records, etc.).

## Activation sequence (must be respected)

1. Slice 1 Source Ownership and Ingestion Proposal reviewed and approved.
2. This handoff note promoted from DRAFT to RECORDED (status updated, owner recorded).
3. Implementation of the `CREATE TABLE IF NOT EXISTS` migration in `automation_db.py`.
4. Verification: a fresh DB initializes both tables; existing features unaffected;
   dropping the tables restores prior state.
5. Only after steps 1-4: begin the Slice 1 scaffold in `scripts/aivsb/retrieval/`.

## Signature (to be filled on activation, not before)

- Writer: Hermes (reasoning/strategy lane)
- Receiver: (editing session or assigned owner)
- Commit hash: (filled on execution)
- Affected regions: `automation_db.py` schema-init section only
