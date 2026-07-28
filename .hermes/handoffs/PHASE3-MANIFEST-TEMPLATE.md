---
status: DRAFT
manifest_schema_version: phase3-frozen-manifest-v2-slice2r
fixture_freeze_authorized: false
---

# Phase 3 Frozen Manifest Template

Canonical JSON is UTF-8, sorted keys, compact separators, one newline, and no
NaN/Infinity. Any changed byte requires a new freeze ID.

```yaml
schema_version: phase3-frozen-manifest-v2-slice2r
finalized: true
freeze_id: <id>
created_at_utc: <timestamp>
subject:
  implementation_commit: 5eed6e1823bc398084e8a46998186771a5970347
  promo_copy_blob_sha256: e3f0bd147cd98d5ff05b0fe1d31762bbc8867e68a8fec40a75e164e8634e19be
  subject_path_hashes: {<path>: <sha256>}
harness:
  commit: <full sha>
  phase3_eval_blob_sha256: <sha256>
source:
  repo_root_identity: <canonical label>
  commit: <full sha>
  clean: true
  corpus_manifest_sha256: <sha256>
model:
  model_id: sentence-transformers/all-MiniLM-L6-v2
  revision: <immutable revision>
  manifest_sha256: <sha256>
  hashes_verified: true
  offline_verified: true
  dimension: <integer>
index:
  database_relative_path: index/automation_state.db
  run_id: <id>
  status: COMPLETED
  extractor_version: <version>
  manifest_hash: <hash>
  chunk_count: <integer>
  embedding_count: <integer>
  membership_sha256: <sha256>
fixtures:
  schema_version: phase3-fixture-v2-slice2r
  path: fixtures.json
  sha256: <sha256>
  fixture_count: 24
scoring:
  automated_scorer_version: phase3-eval-v1
  attempt_schema_version: phase3-attempt-v2-slice2r
  quality_rubric_version: phase3-quality-rubric-v2
  safety_rubric_version: phase3-safety-rubric-v2
  threshold_policy_version: phase3-thresholds-v2
  scorer_sha256: <sha256>
  quality_rubric_sha256: <sha256>
  safety_rubric_sha256: <sha256>
  threshold_policy_sha256: <sha256>
normal_runtime_default: false
fixture_freeze_approval_sha256: <sha256>
```

Freeze fails if the source checkout is dirty, the model revision is null or
mutable, offline verification fails, index status is not `COMPLETED`, counts or
hashes disagree, fixture count is not 24, governing versions are missing, or the
subject does not equal `5eed6e1...`.

The canonical local root is
`.hermes/evidence/aivsb-phase3/freezes/<freeze_id>/`. No such finalized directory
is authorized or created by the harness/design slice.
