---
status: RECORDED
recorded: true
executed: false
handoff_id: AIVSB-RETRIEVAL-PROVENANCE
revision: 2026-07-27
depends_on_commit: "2100123 (Slice 1 derived retrieval index)"
approved_by: David (repository owner)
purpose: Follow-up lane to persist run-level retrieval index provenance.
review_gate: "None — authorized directly by user as a separate, narrowly scoped lane."
tags: [handoff, automation-db, slice-1, aivsb, provenance, retrieval]
---

# Handoff - AIVSB retrieval index provenance (run-level metadata)

**handoff_id:** `AIVSB-RETRIEVAL-PROVENANCE` · **revision:** 2026-07-27
**depends_on_commit:** `2100123` (Slice 1 derived retrieval index, published to
`backup/2026-07-13`).
**Approved_by:** repository owner. This is a separate, explicitly authorized lane,
not part of commit `2100123`.

## Why the shared file is being touched

Commit `2100123` delivered the Slice 1 derived retrieval index
(`retrieval_chunks`, `chunk_embeddings`) but deferred run-level provenance under a
recorded scope amendment. This lane closes that gap: it persists enough run-level
metadata to answer "which AIVSB source state, extractor implementation, and embedding
configuration produced the current derived index?" without changing retrieval
behavior.

## Explicit scope

- Additive `CREATE TABLE IF NOT EXISTS` migration for:
  - `retrieval_index_runs` (run-level provenance: canonical repo root, source Git
    commit + dirty flag, extractor version, embedding model/revision, manifest hash,
    chunk/embedding counts, lifecycle timestamps, status, error message).
  - `retrieval_index_run_chunks` (audit-safe membership snapshot: `run_id`,
    `chunk_id`, `content_hash`; FK to `retrieval_index_runs(run_id)` ON DELETE CASCADE
    only — NOT to `retrieval_chunks`).
- No mutation of `retrieval_chunks` / `chunk_embeddings` schema.
- No change to retrieval ranking, prompt composition, feature flags, or Slice 2
  consumer behavior.
- No `app.py` integration.

## Schema versioning decision (DECIDED, recorded)

- **`SCHEMA_VERSION` is incremented 6 -> 7 in this lane.**
- Rationale (materially different from Slice 1): `retrieval_index_runs` is
  **durable governance/audit metadata**, not a rebuildable derived cache. Run records
  are intended to survive index rebuilds, constitute audit evidence, and are NOT
  reconstructable solely from the current live index. This is the explicit exception
  to the Slice 1 convention (where additive derived caches did not advance
  `SCHEMA_VERSION`). The Slice 1 convention stands for `retrieval_chunks` /
  `chunk_embeddings`; this lane's run tables are a new durable schema that warrants a
  version bump so future migration tooling can distinguish schema 6 from 7.
- A future provenance-schema change is its own additive migration + explicit handoff.

## Membership schema decision (audit-safe)

- `retrieval_index_run_chunks` stores an **immutable snapshot** of membership:
  `(run_id, chunk_id, content_hash)` with `content_hash` captured at run time.
- FK references `retrieval_index_runs(run_id)` ON DELETE CASCADE **only**. It does NOT
  FK to `retrieval_chunks`. This is deliberate: historical membership must survive
  later live-row deletion (e.g. a chunk removed by a subsequent `sync_chunks`). If it
  FK'd to `retrieval_chunks`, removing a live chunk would cascade-delete its historical
  membership, destroying audit evidence. The `content_hash` in the snapshot preserves
  what the chunk was at index time even after the live row is gone.

## Lifecycle (two-phase, audit-friendly)

1. Resolve source root.
2. Collect Git state (commit SHA + dirty; NULL commit if not a Git checkout).
3. Extract chunks.
4. Build deterministic manifest hash (sorted: relative path, file content sha,
   extractor version, embedding model/revision, relevant config; no timestamps,
   absolute paths, row order, or temp paths).
5. Insert `STARTED` run record (committed).
6. Synchronize chunks + embeddings atomically (Slice 1 `sync_chunks`).
7. Insert run-to-chunk membership snapshot (with content_hash).
8. Record final counts; mark run `COMPLETED`.
- On failure during 6/7/8: mark run `FAILED`, record error summary, propagate the
  exception. Never mark `COMPLETED` on failure.
- The `STARTED` record is committed before the index mutation so failed runs remain
  evidenced even if the mutation rolls back.

## Extractor version policy

- Explicit constant `EXTRACTOR_VERSION = "slice1-extractor-v1"` in the retrieval
  package (not derived from package timestamps). Enforced in the manifest hash.

## Known gaps / out of scope

- No automatic rejection of dirty Git sources (the handoff does not make clean state
  mandatory; dirty is recorded honestly as `source_git_dirty=1`).
- `extractor_code_hash` is optional and not included in this lane (explicit version
  policy is enforced instead).
- Phase 2 consumer wiring (recording `run_id`/`manifest_hash` on retrieval results) is
  NOT part of this lane and remains separately governed.

## Dependencies

- Depends on commit `2100123` (the `retrieval_chunks` / `chunk_embeddings` tables).
- `AIVSB_SOURCE_PATH` supplied as a deployment prerequisite (unchanged from Slice 1).

## Out of scope (explicitly excluded)

- Copying/vendoring the AIVSB corpus; modifying the external repository.
- Retrieval ranking or embedding changes; BGE-M3 introduction.
- Feature-flag or `app.py` changes; Slice 2 consumer integration.
- Any Visual Director / image-generation code.

## Committed files (isolated)

- `automation_db.py` (SCHEMA_VERSION 6->7 + two new tables)
- `scripts/aivsb/retrieval/provenance.py` (new)
- `scripts/aivsb/retrieval/index_store.py` (wired to provenance lifecycle)
- `scripts/aivsb/retrieval/cli.py` (orchestrates lifecycle)
- `scripts/aivsb/retrieval/__init__.py` (exports)
- `tests/aivsb/test_retrieval_provenance.py` (new)
- `.hermes/handoffs/AIVSB-RETRIEVAL-PROVENANCE-HANDOFF.md` (this file)

No `app.py`, prompt composer, policy gate, Visual Director code, or Slice 2
integration enters this commit. No push without explicit authorization.
