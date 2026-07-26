# Handoff: Rendered A/B harness (evidence gate, orchestration + evaluation only)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: (run `git rev-parse --short HEAD`; this is the harness/evaluation commit.)
Parent: `5e3e10e` (env-gated integration), `d2fae2c` (Slice 1 + review), `93b9241`.

## Intent
Build the configured control experiment that decides whether the Visual Director
integration improves ASSETS (not just prompt text). This commit is STRICTLY
orchestration + evaluation:
  - capture the exact 3 legacy + 3 Director prompts from the real production path
  - a pluggable RenderBackend (MockBackend for free tests; RecordedBackend for
    real traces supplied by the operator)
  - the 7-criterion 1-5 scoring rubric + the continue/stop gate
  - manifest (JSON) + review-sheet (MD) writers
  - tests using MOCKED generation (no cost, no network)

It does NOT:
  - call any external provider (no cost-bearing generation in this commit)
  - install Diffusers / change providers / add reference images / LoRA / etc.
  - touch production metadata, approved image banks, or TikTok packs
  - modify AIVSB, the Director logic, or the Bible
  - implement Slice 2
AIVSB remains frozen. The real 6-image render is a SEPARATE, cost-authorized step.

## Files (isolated)
- tests/render_ab/harness.py  (capture + backend + run_ab + RUBRIC + gate + writers)
- tests/render_ab/test_harness.py (7 tests, MockBackend, offline)

## Verification (this commit)
7/7 A/B harness tests pass (capture, 6-image run, manifest+report, gate
tie-rejection, gate canon-regression-rejection, gate clear-win, sandbox isolation).
Also: 5 Slice-1 unit tests + 5 integration tests still pass.

## Control (single variable = prompt)
legacy = make_chapter_image_prompts(..., VISUAL_DIRECTOR off, AIVSB off)
director = make_chapter_image_prompts(..., VISUAL_DIRECTOR on)
Same scene, provider, model, size, quality, count. Only the prompt differs.

## Known prompt artifact (recorded, NOT fixed here)
The Director output emits "silver edged weapon, silver edged" - the canonical
weapon appears twice (malformed `silver_edged_weapon` coerced + canonical
`silver edged`). Redundant, not disqualifying, but a prompt-quality defect.
Recommended follow-up: dedup weapon tokens in _appearance_lock (separate commit,
NOT in this orchestration slice). Flagged in the report template.

## Next step (NOT in this commit; needs explicit cost authorization)
Render the 6 images via ONE engine for both paths (FLUX 2 / FAL via the Hermes
image tool is the only executable engine this session; the app's diffusers path
is unavailable - deps missing). Capture the REAL provider+model trace per call
(because the configured image_sources label may not reflect the engine that
actually rendered). Score with the rubric, apply the gate. A tie is not enough;
a prettier isolated image is not enough - the Director must improve the usable
sequence.

## Gate (from directive)
Recommend continue ONLY when ALL:
  - overall_improvement Director > Legacy (Director wins overall)
  - canon_accuracy Director >= Legacy (no regression)
  - >= 2 of 3 Director images keep recognizable Liang identity
  - three-shot sequence visibly differentiated (shot_differentiation >= 4)
