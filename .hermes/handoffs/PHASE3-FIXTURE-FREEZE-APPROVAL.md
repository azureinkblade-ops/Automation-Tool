---
status: CLOSED
approved: false
executed: false
fixture_freeze_authorized: false
phase3_execution_authorized: false
feature_enabled: false
push_authorized: false
subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
harness_commit: a263b31a34f1013a2dbc78a90743bd08c6e0b079
---

# Phase 3 Fixture-Freeze Approval

## Current decision

Fixture freeze is not authorized. The present harness/design work may validate
schemas and preflight proposals only. It may not select fixtures, build an index,
or create `.hermes/evidence/aivsb-phase3/freezes/<freeze_id>/`.

## Required future approval

```yaml
PHASE3_FIXTURE_FREEZE_APPROVAL:
  subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
  harness_commit: <exact local commit>
  source_commit: <approved clean AIVSB source commit>
  model_id: sentence-transformers/all-MiniLM-L6-v2
  model_revision: <immutable revision>
  model_manifest_sha256: <sha256>
  fixture_schema_version: phase3-fixture-v2-slice2r
  quality_rubric_version: phase3-quality-rubric-v2
  safety_rubric_version: phase3-safety-rubric-v2
  threshold_policy_version: phase3-thresholds-v2
  governing_hashes:
    fixture_schema: <sha256>
    quality_rubric: <sha256>
    safety_rubric: <sha256>
    threshold_policy: <sha256>
  approved: false
  approved_by: ""
  approved_at_utc: ""
```

Only David may change `approved` to true.

## Scope of a future true approval

It may authorize clean worktree creation, candidate validation, offline model
verification, isolated index materialization, manifest hashing, and finalizing
one no-overwrite freeze directory. It does not authorize OFF/ON attempts,
feature activation, push, deployment, publication, or production writes.

## Freeze blockers

- candidate count/allocation/focus mismatch;
- unresolved product labels;
- dirty source checkout;
- mutable or null model revision;
- failed model file-hash or offline verification;
- index status not `COMPLETED`;
- subject drift from `5eed6e1...`;
- scorer/rubric/threshold hash mismatch;
- normal runtime default not OFF.
