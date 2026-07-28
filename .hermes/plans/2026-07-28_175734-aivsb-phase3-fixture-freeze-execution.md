# AIVSB Phase 3 Fixture-Freeze and Execution Plan

> **For Hermes:** Execute this plan only after the named governance gate for each phase is explicitly approved. Fixture-freeze approval does not authorize evaluation execution. Execution approval does not authorize feature activation, push, deployment, or publication.

**Goal:** Freeze a reproducible 24-fixture AIVSB evaluation package against implementation commit `5eed6e1823bc398084e8a46998186771a5970347`, then run a controlled, failure-inclusive OFF/ON study that measures safety, deterministic fallback reliability, and output effectiveness without changing the production default.

**Architecture:** Build one deterministic local evaluation harness around the committed `promo_copy.build_platform_posts()` contract. Materialize the AIVSB corpus and retrieval index in clean isolated worktrees, freeze all inputs/scoring rules as hash-bound artifacts, require a separate manifest-bound execution approval, and run each OFF/ON attempt in a fresh subprocess. Raw attempt records are authoritative; blinded quality packets and unblinded safety packets are derived from them. The harness may set `ENABLE_AIVSB_RETRIEVAL=true` only in ON-arm subprocesses; normal runtime remains OFF.

**Tech stack:** Python 3.11, pytest, stdlib `json`/`hashlib`/`sqlite3`/`subprocess`, existing `promo_copy.py`, existing `scripts/aivsb/retrieval/*`, Git clean worktrees, local SQLite, Markdown governance records.

---

## 1. Current authoritative state

```yaml
harness_design_status: IMPLEMENTED_AND_VERIFIED_LOCALLY
harness_design_authorized_at_utc: 2026-07-28T18:10:00Z
harness_commit: a263b31a34f1013a2dbc78a90743bd08c6e0b079
harness_verified_at_utc: 2026-07-28T18:32:38Z
fixture_candidate_preparation_authorized: true
fixture_freeze_authorized: true
fixture_freeze_authorized_at_utc: 2026-07-28T19:06:08Z
phase3_execution_authorized: false
feature_enabled_in_normal_runtime: false
push_authorized: false
deployment_authorized: false
publication_authorized: false
subject_implementation_commit: 5eed6e1823bc398084e8a46998186771a5970347
slice2r_closure_commit: cd53c04ad05b9abbbe78d857cfb9f906a6563860
```

Verified planning facts:

- `promo_copy.py` at current HEAD is byte-identical to the blob at `5eed6e1` (`SHA-256 e3f0bd147cd98d5ff05b0fe1d31762bbc8867e68a8fec40a75e164e8634e19be`, 65,391 bytes); Slice 2R is the production subject under evaluation.
- The live Automation Tool `automation_state.db` currently has no `COMPLETED` `retrieval_index_runs` record. Phase 3 must build an isolated evaluation index; it must not reuse or mutate the live database.
- The canonical AIVSB checkout is currently at `e992c4446e6581cf665e904d277608992cd4db65` but has untracked evaluation/model artifacts. Freeze must use a clean Git worktree at an explicitly approved source commit, not the dirty checkout.
- The AIVSB repo contains tracked MiniLM acquisition/verification artifacts (`retrieval/model_acquisition/minilm_manifest.json`, downloader, promoter, and offline verifier). Evidence-grade freeze requires the tracked manifest, immutable revision, per-file hashes, and successful offline verification.
- Phase 3 is deterministic template evaluation. No GPU, image generation, paid provider, LLM composition, social publishing, or production writes are required.

## 2. Non-negotiable boundaries

1. The only causal variable in Study A is `ENABLE_AIVSB_RETRIEVAL` (`false` vs `true`).
2. Same fixture, subject code, source corpus, derived index, rotation stub, ledger state, release state, requested focus, process environment, and serialization rules in both arms.
3. Production/default value remains `false`; ON is allowed only in an isolated evaluation subprocess after execution approval.
4. No changes to query construction, ranking, embeddings, domain mapping, caption templates, CTA/release objectives, public return schema, or retrieval fallback logic during the study.
5. No use of the live Automation Tool database or dirty AIVSB source checkout.
6. No raw retrieval body, query, chunk ID, manifest metadata, or private canary may enter a public output or blinded quality packet.
7. Retrieval provenance is sink-only. `injected_chunk_ids` remains `[]`; Phase 3 uses `signal_consumption` and `retrieval_influence`, never “injection coverage.”
8. Backend/fault failures remain in their correct denominators. Missing evidence is `NOT_MEASURED`, never silently omitted or passed.
9. Phase 3 produces evidence and a recommendation only. Activation is a later, separate decision.
10. No commit, push, fixture freeze, evaluation execution, deployment, publication, or feature activation is implied by this plan.

## 3. Canonical local artifact layout

Canonical root (local, no-publish):

`C:\Users\David\Documents\Automation tool\.hermes\evidence\aivsb-phase3\`

```text
.hermes/evidence/aivsb-phase3/
  freezes/
    <freeze_id>/
      candidate-inventory.json
      fixtures.json
      canon/
        FX-EN-001.json
        ...
      source-manifest.json
      model-manifest.json
      index/
        automation_state.db
        index-manifest.json
      scorer-manifest.json
      frozen-manifest.json
      frozen-manifest.sha256
      validation-report.json
      FINALIZED
  runs/
    <run_id>/
      approval.json
      preflight.json
      raw/
        FX-EN-001__OFF.json
        FX-EN-001__ON.json
        ...
        C-ZERO-HITS.json
        ...
      packets/
        quality/
          FX-EN-001__A.json
          FX-EN-001__B.json
          ...
        safety/
          FX-EN-001.json
          ...
        sealed-arm-map.json
      reviews/
        quality-reviewer-1.jsonl
        quality-reviewer-2.jsonl
        adjudication.jsonl
        safety-review.jsonl
      aggregates/
        metrics.json
        denominators.json
        case-table.jsonl
      report.json
      report.md
      artifact-index.json
      artifact-index.sha256
      FINALIZED
```

Rules:

- Raw attempt JSON is authoritative.
- Canonical JSON encoding: UTF-8, sorted keys, compact separators, newline at EOF, no NaN/Infinity.
- Every file gets SHA-256 in `artifact-index.json`.
- `frozen-manifest.json` and finalized run artifacts are no-overwrite. Any changed byte requires a new `freeze_id` or `run_id`.
- `FINALIZED` contains the ordered bundle hash and creation timestamp; the harness refuses to mutate a directory containing it.
- Private artifact root remains local and untracked unless David separately authorizes a sanitized evidence commit.

## 4. Authorized harness/design implementation

Authorized by David at `2026-07-28T18:10:00Z`:

- Create `scripts/aivsb/phase3_eval.py` as a validation-only harness.
  - Authorized commands: `capabilities`, `validate-candidates`,
    `freeze-preflight`, `execution-preflight`.
  - Fixture-freeze and evaluation-execution capabilities remain disabled.
  - The module must not import or invoke `promo_copy`, build an index, or create a
    finalized fixture/run artifact.
- Create `tests/aivsb/test_phase3_eval.py` with disposable synthetic data only.
- Revise the seven Phase 3 draft documents for Slice 2R.
- Create separate harness/design and fixture-freeze approval records.

Future action-capable `freeze`, `run`, packet, finalization, and reporting paths
require separately scoped authorization. The harness/design commit may contain
only Phase 3 plans, handoffs, validation tooling, and tests. It must not modify
`promo_copy.py`, `automation_db.py`, `app.py`, or `scripts/aivsb/retrieval/*`.

## 5. Required correction of the existing Phase 3 draft package

Before fixture-freeze authorization is requested, revise all seven draft documents to match Slice 2R:

1. Replace the stale Slice 2R blocker with `slice_2r_complete: true` and subject commit `5eed6e1...`.
2. Remove `composer_prompt_or_context`, `retrieved_context_block`, delimiter, and raw-block scoring fields.
3. Replace “injected context/coverage” with:
   - `retrieval_return_coverage`: ON attempts with nonempty `returned_chunk_ids` / 24;
   - `signal_consumption_rate`: ON attempts with nonnull `derived_signal` / 24;
   - `retrieval_influence_rate`: paired cases where ON `caption_style` differs from OFF `caption_style` / 24.
4. Preserve `injected_chunk_ids: []` only as a legacy compatibility assertion.
5. Define the ON safety record from `retrieval_eval_sink`:
   `run_id`, `manifest_hash`, `query`, `returned_chunk_ids`, `fallback_reason`, `signal_fallback_reason`, `derived_signal`, source IDs/rank/domain.
6. Define safety evidence as sink provenance plus chunk metadata resolved from the frozen evaluation index. Raw bodies may exist only in the private safety packet, never in runtime sink or blinded packets.
7. Change the OFF baseline from `c9e39c5` to the same subject implementation commit `5eed6e1...` with the flag OFF.
8. Add the Slice 2R closure commit as governance provenance, not as the runtime subject.
9. Replace `embedding_revision: <revision or null>` with a mandatory immutable revision and tracked model-manifest SHA.
10. Add the two separate approval records and manifest-hash binding described below.
11. Remove the malformed `***` list marker currently present in the execution-approval draft.
12. Version and hash the rubric, thresholds, automated scorer, fixture schema, and attempt schema.

Verification command after the document revision:

```bash
grep -RInE 'composer_prompt_or_context|retrieved_context_block|injection coverage|BLOCKED on Slice 2R|embedding_revision:.*null' .hermes/handoffs/PHASE3-*.md
```

Expected: no stale contract hits except explicit historical/negation notes.

## 6. Gate A: harness-design authorization

A later authorization must permit only:

- creating `scripts/aivsb/phase3_eval.py` and `tests/aivsb/test_phase3_eval.py`;
- revising the eight Phase 3 governance documents;
- running deterministic unit tests and static validators;
- making an isolated local harness/design commit if green.

It must not permit fixture freezing or OFF/ON execution.

Harness acceptance gates:

- `python -m pytest tests/aivsb/test_phase3_eval.py -q` passes;
- `python -m pytest tests/aivsb -q` passes;
- dry-run test proves `build_platform_posts` call count is zero;
- harness commit changes no production/retrieval file;
- subject-path diff is empty:

```bash
git diff --exit-code 5eed6e1823bc398084e8a46998186771a5970347 -- \
  promo_copy.py automation_db.py scripts/aivsb/retrieval
```

If a later closure/documentation commit changes only `.hermes/`, compare against the harness commit’s parent production tree or use an explicit subject-file hash allowlist.

## 7. Candidate fixture qualification (pre-freeze, no retrieval execution)

### 7.1 Allocation

Freeze exactly 24 fixtures:

| Novel | Canonical ID | Count | Required focus coverage |
|---|---:|---:|---|
| Eternal Nexus | `en` | 6 | one each: `royal_road_live`, `patreon_early`, `youtube_release`, `weekly_general_promo`, `catch_up_archive`, `generic` |
| Heavenly Ascension System | `ha` | 6 | same six |
| The Hundredfold Path | `hp` | 6 | same six |
| Soul Forge Era | `sf` | 6 | same six |

A fixture is one deterministic `build_platform_posts()` call producing the complete public result bundle.

### 7.2 Fixture fields

Each fixture must contain:

```yaml
fixture_id: FX-EN-001
novel_id: en
chapter_id: "..."
requested_focus: royal_road_live
composer_inputs: {abbr, novel, chapter, title, phrases, characters, ...}
rotation_stub:
  version: phase3-rotation-stub-v1
  return_index: 0
ledger_state: {...}
release_status: {...}
canon_reference:
  source_files: [relative/path.yaml]
  source_hashes: [sha256]
  relevant_facts: [explicit product-reviewed facts]
  prohibited_claims: [explicit product-reviewed claims]
expected_contract:
  public_keys: [caption, patreon_note, facebook_post, x_post, x_thread_links, post_focus, caption_style, tracking_campaign, _agent_source]
  scored_text_fields: [caption, patreon_note, facebook_post, x_post]
  leak_checked_fields: ALL_RECURSIVE
qualification:
  product_reviewed: true
  selected_without_observing_on_output: true
```

### 7.3 Qualification rules

- Select cases from production-shaped chapter/promo inputs, not synthetic retrieval outcomes.
- Do not run ON retrieval while choosing cases.
- Do not choose fixtures because they are known to retrieve or improve.
- Canon facts/prohibited claims come from approved source files and David’s product review, never from the retrieval result.
- Every source path must exist in the clean source worktree and match its frozen hash.
- Every `characters` entry must resolve to the intended novel/canon or be explicitly marked absent.
- No secrets, credentials, live URLs with tokens, or private filesystem paths in fixture JSON.
- Any unresolved product label sets `qualification.status: needs_product_review`; such a fixture cannot freeze.

Static validator must fail with exit 2 on:

- count != 24;
- allocation != 6/6/6/6;
- missing focus cell;
- duplicate fixture ID;
- missing/dirty source identity;
- missing canon hash/fact/prohibited-claim review;
- output-key contract mismatch;
- any `needs_product_review` fixture;
- selection metadata indicating ON output was observed before freeze.

## 8. Scorer, rubric, and threshold freeze

Proposed version labels (labels are insufficient without hashes):

```yaml
automated_scorer_version: phase3-eval-v1
attempt_schema_version: phase3-attempt-v2-slice2r
fixture_schema_version: phase3-fixture-v2-slice2r
quality_rubric_version: phase3-quality-rubric-v2
safety_rubric_version: phase3-safety-rubric-v2
threshold_policy_version: phase3-thresholds-v2
```

The frozen manifest records each governing file’s SHA-256 and, for code, Git blob ID.

### 8.1 Mechanical scorer responsibilities

- validate hashes/schema/public keys;
- compute OFF identity and recursive leak checks;
- compute retrieval-return, signal-consumption, and actual-influence rates;
- compute all numerators/denominators from raw records;
- produce blinded packets and sealed arm map;
- ingest structured reviewer grades without inferring missing fields;
- regenerate aggregate JSON deterministically;
- never choose or alter thresholds.

### 8.2 Reviewer protocol

Preferred: two independent blinded quality reviewers, followed by adjudication.

Fallback: one blinded reviewer plus a frozen six-fixture repeat subset selected before scoring.

Quality reviewers receive only arm-neutral A/B files containing public text fields. They do not receive `caption_style`, queries, hit IDs, provenance, fixture expected signal, or arm labels.

Safety reviewer receives the separate unblinded safety packet only after quality scoring for that fixture is sealed.

Every grade records fixture ID, output field, grade, bounded evidence note, reviewer ID, rubric version/hash, and timestamp. Missing evidence is `INVALID_PENDING_AUDIT`.

### 8.3 Proposed gates for threshold-policy review

These are proposed for explicit approval before freeze; they are not authorized by this plan.

Safety and reliability, zero tolerance:

- public retrieval/canary leak: 0 of 24 ON and 0 of 24 OFF;
- cross-novel selected signal source: 0 of 24 ON;
- ON-only canon contradiction: 0 of 24 ON;
- frozen manifest/index mismatch: 0 of 24 ON;
- OFF identity breach: 0 of 24 OFF;
- Study C contract failures: 0 of the frozen Study C cases;
- audit completeness: 24 of 24 paired cases.

Effectiveness, evaluated only if safety/reliability pass:

- mean paired quality delta (scale -2..+2) >= +0.25;
- regression cases <= 3 of 24;
- mean canon-error reduction >= 0;
- conditional signal relevance >= 3.0 when a signal is consumed;
- all 24 cases remain in full-set calculations; no-signal/no-output-change contributes zero effect, not omission.

Reject activation eligibility if any safety gate fails, mean quality delta < 0, regression cases > 6 of 24, or net canon harm < 0. Everything else is `AMBIGUOUS_REQUIRES_SEPARATE_DECISION`; it does not authorize tuning.

David must approve or amend these thresholds before fixture freeze. No threshold changes are allowed after the manifest hash is approved.

## 9. Gate B: fixture-freeze authorization

Create `.hermes/handoffs/PHASE3-FIXTURE-FREEZE-APPROVAL.md` with this initially closed record:

```yaml
PHASE3_FIXTURE_FREEZE_APPROVAL:
  subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
  harness_commit: "<required local commit>"
  source_commit: "<approved AIVSB source commit>"
  fixture_schema_version: phase3-fixture-v2-slice2r
  rubric_version: phase3-quality-rubric-v2
  threshold_version: phase3-thresholds-v2
  approved: false
  approved_by: ""
  approved_at_utc: ""
```

`approved: true` authorizes only:

- clean worktree creation;
- static candidate validation;
- offline model verification;
- isolated index materialization;
- fixture/canon/model/index/scorer manifest hashing;
- writing and finalizing `freezes/<freeze_id>/`.

It does not authorize running OFF/ON attempts.

## 10. Fixture-freeze procedure (after Gate B only)

1. Re-check `git rev-parse` for Automation Tool and AIVSB source repositories.
2. Create a clean Automation Tool evaluation worktree at the approved harness commit.
3. Prove production subject paths are unchanged from `5eed6e1...`.
4. Create a clean AIVSB source worktree at the approved source commit; do not copy from the dirty live checkout.
5. Verify tracked `minilm_manifest.json` hashes and load the immutable snapshot with offline mode (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`). Abort if revision/hash/dimension is missing or mismatched.
6. Validate candidate inventory statically; no ON call.
7. Copy approved fixtures/canon references into a new `freezes/<freeze_id>.tmp/` directory.
8. Initialize a new isolated `automation_state.db` under that freeze directory.
9. Extract the real production chunk set from the clean source worktree and build the index once with the pinned backend.
10. Require a `COMPLETED` provenance row; record run ID, source commit/clean state, extractor version, model/revision, manifest hash, chunk count, embedding count, and membership hashes.
11. Assert every referenced source/chunk ID exists in the frozen source/index.
12. Record subject commit and Git blob hashes for `promo_copy.py`, `automation_db.py`, and `scripts/aivsb/retrieval/*`.
13. Record fixture, schema, scorer, rubric, threshold, source, model, and index hashes.
14. Run freeze validator. Expected: zero errors, zero unresolved fields.
15. Atomically rename `.tmp` to `<freeze_id>/`, write `FINALIZED`, and calculate `frozen-manifest.sha256`.
16. Re-open and independently recalculate every hash. A mismatch invalidates the freeze.
17. Record the freeze ID and manifest SHA in the Phase 3 handoff. Do not run attempts.

## 11. Gate C: manifest-bound execution authorization

Revise `.hermes/handoffs/PHASE3-EXECUTION-APPROVAL.md` to require:

```yaml
PHASE3_EXECUTION_APPROVAL:
  subject_commit: 5eed6e1823bc398084e8a46998186771a5970347
  harness_commit: "<exact commit>"
  frozen_manifest_path: ".hermes/evidence/aivsb-phase3/freezes/<freeze_id>/frozen-manifest.json"
  frozen_manifest_sha256: "<exact sha256>"
  quality_rubric_sha256: "<exact sha256>"
  safety_rubric_sha256: "<exact sha256>"
  threshold_policy_sha256: "<exact sha256>"
  reviewer_protocol: "two-independent-plus-adjudication | one-plus-frozen-repeat-subset"
  reviewer_ids: ["<identified reviewers>"]
  controlled_on_flag_allowed: true
  normal_runtime_default_must_remain_off: true
  approved: false
  approved_by: ""
  approved_at_utc: ""
```

Only David may create the explicit `approved: true` event. Any manifest byte change invalidates approval.

## 12. Execution preflight (after Gate C only)

The preflight performs no composition attempts.

- verify approval signature and exact manifest SHA;
- verify clean harness worktree and unchanged subject paths;
- verify `ENABLE_AIVSB_RETRIEVAL` defaults false in the committed subject;
- verify isolated evaluation DB path and refuse the live repository DB;
- verify source/model/index/fixture/scorer/rubric/threshold hashes;
- verify offline backend load and expected embedding dimension;
- verify 24 fixtures and all source/chunk references;
- verify output root is new and not finalized;
- verify no publishing credentials/routes are initialized;
- verify dry-run call count for `build_platform_posts` is zero;
- write `preflight.json` with pass/fail evidence.

Any failure exits nonzero before Study A/B/C.

## 13. Controlled execution procedure

### 13.1 Study C first: deterministic reliability/fault contract

Freeze exact cases and expected outcomes before execution:

1. `zero_hits`: retrieve returns `[]`; public output equals OFF; `fallback_reason=no_hits`.
2. `retrieval_exception`: retrieve raises controlled `sqlite3.OperationalError`; public output equals OFF; normalized `retrieval_error:OperationalError`.
3. `no_mappable_domain`: returned hits exist but no mapped domain; public output equals OFF; `signal_fallback_reason=no_mappable_domain`.
4. `cross_novel_only`: returned hits are foreign novel; no signal consumed; no leak.
5. `no_active_manifest`: `get_active_index_run` returns null; attempt is quarantined as setup/manifest failure even if public output exists.
6. `manifest_mismatch`: runner refuses the attempt before scoring.
7. `provenance_lookup_exception`: current consumer re-raises setup defects outside the contained retrieval boundary; runner records a terminal `setup_failure`. This is not mislabeled as graceful fallback.

If Study C violates a frozen expectation, stop before Study A. Changing runtime behavior requires a separate remediation authorization.

### 13.2 Study A: paired effectiveness

For each of 24 fixtures:

1. Start a fresh OFF subprocess with `ENABLE_AIVSB_RETRIEVAL=false`.
2. Load the same frozen index snapshot read-only and identical deterministic stubs.
3. Run one `build_platform_posts` call; capture complete public result; expect no sink record.
4. Start a fresh ON subprocess with `ENABLE_AIVSB_RETRIEVAL=true`.
5. Run the identical fixture/stubs; capture public result and exactly one sink record.
6. Restore/verify the parent environment remains OFF after subprocess exit.
7. Write terminal raw records for both attempts, including elapsed time and normalized failure.
8. Compare public schemas recursively and run canary/leak checks.
9. Compute whether signal was returned, consumed, and actually influenced `caption_style`.
10. Continue all 24 cases unless a hard-stop condition below applies.

Attempt order may be randomized from a frozen seed, but each attempt runs in a fresh subprocess so mutable module/rotation state cannot cross arms.

### 13.3 Study B: retrieval safety

Derived from the 24 ON attempts; no second runtime call.

For each case, build a private safety packet containing:

- fixture and frozen canon references;
- query;
- returned chunk IDs in retrieval order;
- frozen chunk metadata/domain/source hash and bounded private body evidence;
- selected signal source ID/rank/domain;
- derived signal;
- retrieval and signal fallback reasons;
- manifest/run identity;
- recursive public-output leak result;
- cross-novel and canon-consistency verdict fields.

Safety packet never enters the blinded quality review.

### 13.4 Hard-stop conditions

Stop further attempts only for:

- writes to live/production database or state;
- output publication or external side effect;
- manifest/index/source drift;
- broken worktree/process isolation;
- private retrieval evidence escaping the canonical private artifact root;
- corrupted frozen fixture/index state.

An ordinary safety-gate failure blocks activation eligibility but does not truncate the 24-case denominator.

## 14. Blinding and review

1. After all raw attempts are finalized, derive quality packets containing only `caption`, `patreon_note`, `facebook_post`, and `x_post`.
2. Use independent per-fixture A/B randomization from a frozen seed.
3. Store arm mapping only in `sealed-arm-map.json`; quality reviewers cannot access it before grade finalization.
4. Score every platform text field separately on the frozen rubric.
5. Per-case regression is worst-of across platforms; continuous quality is the mean with per-platform values retained.
6. Seal quality grades before unblinding or safety review.
7. Conduct unblinded safety review against frozen canon, never against reviewer memory or retrieved text as its own authority.
8. Preserve disagreements; adjudication appends a record and never overwrites reviewer originals.

## 15. Aggregation and final report

Mechanical aggregates must show numerator and denominator for every metric:

- 24 paired cases / 48 Study A attempts;
- 24 ON attempts for retrieval/signal/safety metrics;
- 24 OFF attempts for OFF identity;
- N frozen Study C cases for reliability;
- reviewed output fields for human-score metrics;
- all attempted cases for end-to-end eligibility.

Required result enums:

```text
SAFETY: PASS | FAIL | NOT_MEASURED
RELIABILITY: PASS | FAIL | NOT_MEASURED
EFFECTIVENESS: PASS | FAIL | AMBIGUOUS | NOT_MEASURED
AUDIT_COMPLETENESS: PASS | FAIL
ACTIVATION_ELIGIBILITY: ELIGIBLE_FOR_SEPARATE_DECISION | BLOCKED | NOT_MEASURED
```

Report claims must be labeled `OBSERVED`, `INFERRED`, or `NOT_MEASURED`.

The report may recommend a separate activation decision only when safety, reliability, effectiveness, and audit completeness pass. It must never enable the flag or modify production configuration.

## 16. Verification commands for a future authorized execution

Harness/design phase:

```bash
PYTHONPATH=. python -m pytest tests/aivsb/test_phase3_eval.py -q
PYTHONPATH=. python -m pytest tests/aivsb -q
python -m py_compile scripts/aivsb/phase3_eval.py
```

Freeze phase:

```bash
PYTHONPATH=. python scripts/aivsb/phase3_eval.py validate-candidates --input <candidate-inventory>
PYTHONPATH=. python scripts/aivsb/phase3_eval.py freeze --approval <freeze-approval> --output <freeze-root>
PYTHONPATH=. python scripts/aivsb/phase3_eval.py preflight --manifest <frozen-manifest> --approval <execution-approval> --dry-run
```

Execution phase:

```bash
PYTHONPATH=. python scripts/aivsb/phase3_eval.py run --manifest <frozen-manifest> --approval <execution-approval> --study C
PYTHONPATH=. python scripts/aivsb/phase3_eval.py run --manifest <frozen-manifest> --approval <execution-approval> --study A
PYTHONPATH=. python scripts/aivsb/phase3_eval.py build-packets --run <run-id>
PYTHONPATH=. python scripts/aivsb/phase3_eval.py finalize --run <run-id>
PYTHONPATH=. python scripts/aivsb/phase3_eval.py report --run <run-id>
```

Post-run verification:

- regenerate aggregates from raw and byte-compare;
- independently recalculate artifact-index and bundle hashes;
- assert current production default is still OFF;
- assert no tracked production/retrieval file changed;
- assert no remote push occurred;
- re-open final report and confirm all result enums/denominators are populated or explicitly `NOT_MEASURED`.

## 17. Planned commit boundaries

Only after separate authorization:

1. **Harness/design commit:** Phase 3 docs + `scripts/aivsb/phase3_eval.py` + `tests/aivsb/test_phase3_eval.py`; no production paths.
2. **Fixture-freeze witness commit:** governance record containing freeze ID and manifest SHA only; private fixture/canon/index artifacts remain local unless separately approved.
3. **Execution-result witness commit:** sanitized report/hash references only, and only if David authorizes committing results.

Never combine harness implementation, fixture freeze, evaluation execution, runtime remediation, activation, or push in one authorization/commit.

## 18. Decision sequence

```text
Review and approve this plan
        |
Authorize Phase 3 harness/design work
        |
Build and verify deterministic harness; isolated commit
        |
Review candidate fixtures, rubric, thresholds, source/model identity
        |
Authorize fixture freeze (Gate B)
        |
Materialize clean source + isolated index + frozen manifest
        |
Review manifest and artifact hashes
        |
Authorize manifest-bound execution (Gate C)
        |
Run Study C, then Studies A/B
        |
Seal reviews, aggregate, report safety/effectiveness/reliability
        |
Separate activation decision
        |
Separate push/deployment decision
```

## 19. Immediate next governance decision

The next decision is **not fixture freeze yet**. First review this plan and authorize or reject the bounded Phase 3 harness/design work in Gate A. The currently missing COMPLETED index and dirty source checkout are handled by the planned clean-worktree freeze procedure; no cleanup of the live AIVSB checkout is required.
