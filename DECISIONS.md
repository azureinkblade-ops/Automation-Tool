# Decisions (local, untracked)

This file is intentionally NOT committed. It records deliberate, deferred
decisions so they survive across sessions without entering version control.

## 2026-07-23 — Do NOT propagate cleanup commits to origin/main (DEFERRED)

- The test-cleanup track (commits 7988090, 5305726, df5d979, 9e2b692) is
  published to `origin/backup/2026-07-13` only.
- Propagating these (and the earlier 39 preceding commits, ~43 total) to
  `origin/main` is a SEPARATE, deliberate decision and is DEFERRED.
- Status: intentionally not pushed to origin/main. Revisit only on explicit
  instruction. The backup/2026-07-13 branch remains the published home for
  this work.
- Rationale: the cleanup sequence was verified green on its own branch;
  main propagation is a release/visibility decision, not a correctness one.

## 2026-07-25 — HyperFrames bake-off: SELECTIVELY ADOPT, keep ffmpeg reel builder

- Full record: `docs/adrs/ADR-2026-07-25-hyperframes-bakeoff.md` (committed-ready ADR).
- Decision: do NOT replace `tools/build_ha_reel.py` (ffmpeg) with HyperFrames. HyperFrames
  loses on render speed (10×+), output size (3.3×), simplicity, RAM, and bit-determinism.
- Adopt HyperFrames ONLY as a preview/QA + validation layer: pilot `<hyperframes-player>`
  for in-app preview; optionally port its frame-coverage gate as a pre-render check on the
  ffmpeg builder.
- Evidence: `_eval_hyperframes/` (frozen baseline `d49a6ada…`, HyperFrames repro `d12cbed…`,
  both local/offline). Real `build_ha_reel.py` untouched.
- Status: Accepted. Revisit only if a reel needs HTML/CSS motion ffmpeg can't express, or
  HyperFrames reaches bit-deterministic local renders.
