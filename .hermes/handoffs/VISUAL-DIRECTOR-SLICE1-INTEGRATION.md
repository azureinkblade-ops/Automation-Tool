# Handoff: Visual Director Slice 1 — env-gated integration into app.py

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: (run `git rev-parse --short HEAD`; this is the isolated integration commit.)
Parent: `d2fae2c` (Slice 1 builder + review harness), `93b9241` (Slice 1 builder).

## Intent
Wire `build_visual_scene_package()` into `make_chapter_image_prompts()` BEHIND
`VISUAL_DIRECTOR_ENABLED`, integrated into the existing prompt path only. No
further AIVSB work, no provider changes, no Diffusers, no reference-image work,
no video-pipeline redesign. The prerequisite creative review (handoff
VISUAL-DIRECTOR-SLICE1-REVIEW.md) passed all 8 acceptance checks.

## Files changed (isolated)
- `app.py` — `make_chapter_image_prompts()` (line ~30604): a guarded block at
  the top that, when `VISUAL_DIRECTOR_ENABLED` is truthy, builds the
  VisualScenePackage and returns `package["image_prompts"][:3]` (list[str]).
  Otherwise falls through to the UNCHANGED legacy + AIVSB loop.
- `tests/test_visual_director_integration.py` (new) — 5 integration tests.

## Verified requirements (per the directive)
1. DEFAULT OFF — flag defaults to "" (off). OFF path = legacy. PROVEN
   byte-identical: extracted the pre-change function from HEAD:app.py and
   compared OFF-path output; identical (True).
2. OFF byte-identical to legacy — confirmed (see above).
3. ON returns package["image_prompts"], list[str] preserved — test_on_returns_director_prompts.
4. Fail-soft — any exception / missing Bible path / empty or malformed package /
   insufficient (<3) or non-string prompts -> falls back to legacy prompts.
   Proven by test_failsoft_builder_raises (simulated exception) and
   test_failsoft_missing_bible (nonexistent BIBLE_DIR). Both return 3 prompts,
   no crash, workflow continues.
5. Untouched: AIVSB / retrieval / embeddings / resolver / providers /
   metadata.json schema / video consumers. The Director branch is checked
   BEFORE the AIVSB branch and returns early; the two flags are independent.
   AIVSB lane stays frozen.
6. Prompt count + ordering preserved — Director always returns exactly 3,
   in shot order (establishing / character / action). Callers' [:3]/[:5]
   slicing unchanged.
7. canon_warnings surfaced via existing diagnostics (print) — not persisted to
   any downstream contract. Per-scene warnings logged as
   `[visual-director] canon_warning: ...`.
8. One isolated commit. No cleanup/adjacent refactor bundled.

## Integration test results (codex runtime)
  PASS test_off_default_is_legacy (byte-identical to pre-change)
  PASS test_on_returns_director_prompts (Liang canon tokens present)
  PASS test_on_novel_isolation (Kael EN != Kai HA)
  PASS test_failsoft_missing_bible
  PASS test_failsoft_builder_raises
Also: Slice 1 unit tests (5) + creative review (8 checks) still PASS.

## Next gate (NOT done — explicit directive)
The review proved PROMPT-level improvement, not final ASSET quality. Before
Slice 2, run a real rendered A/B with the current external provider:
  Legacy prompt -> rendered images
  Visual Director prompt -> rendered images
Judge: character identity, canon accuracy, coherent 3-shot sequencing,
readability at mobile size, obvious visual improvement. Do NOT begin Slice 2
until that rendered comparison shows a meaningful gain. AIVSB remains frozen.

## Caveats for the receiver
- `make_chapter_image_prompts` receives full chapter TEXT as `chapter`, but the
  Director expects (novel, chapter_label, scene_text). The integration derives
  scene_text from the curated `phrases` arg (bounded, salient) and passes an
  empty chapter label + lowercased novel id. This is intentional Slice-1 scope;
  richer scene parsing is a later slice.
- Gray (SF) canon is incomplete in the Bible (separate repo); Director omits
  unknown traits and emits a canon_warning. Not a defect in this integration.
- Bible path default: C:\Users\David\Documents\Inkblade Author Studio\scripts\aivsb
  (override via AIVSB_BIBLE_DIR). Missing path -> fail-soft to legacy.
