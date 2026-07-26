# Handoff: Rendered A/B through the REAL application image workflow

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: f3ddf34 (+ this doc correction)
Parent: `af2fa17` (A/B harness + mocked tests), `5e3e10e`, `d2fae2c`, `93b9241`.

## Correction (user-directed, two rounds)
1. First rejected: rendering via the standalone Hermes FLUX 2 (FAL) tool. That is a
   SEPARATE code path that never feeds posts/videos - proves nothing about the
   Director's effect on shipped assets. Retired.
2. Then corrected: "we use stable diffusion as the main source." The app has NO
   FLUX/FAL path. Its image providers are local_stable_diffusion (the MAIN source,
   -> local_image_generator.py with the azink_main LoRA), openai (gpt-image-1),
   google_ai (Gemini, but it mutates promo rotation state -> excluded), banked/
   pexels/pixabay/local_fallback. So the faithful A/B uses LOCAL STABLE DIFFUSION.

## Engine decision
- DEFAULT: LocalSDAppBackend -> app.create_local_stable_diffusion_image's IDENTICAL
  generator command (same local_image_generator.py, SDXL model, azink_main LoRA,
  enhanced prompt, size, scheduler, steps, guidance). Runs on the local GPU ->
  NO API billing. This is exactly the code the posts/videos use.
- ONLY delta from the production function: LocalSDAppBackend deliberately OMITS the
  mark_image_used / save_promo_rotation_state writes, so the A/B does not mutate
  production metadata / promo-rotation DB (per the directive's constraint).
- Alternative: --backend openai (OpenAI gpt-image-1) only if local SD is
  unavailable; that path BILLS and needs ENABLE_EXTERNAL_AI=1 + OPENAI_API_KEY.

## This commit (isolated: orchestration + evaluation only; no generation fired)
- tests/render_ab/harness.py: LocalSDAppBackend (default real path) + OpenAIAppBackend
  (opt-in). Both record the REAL provider trace (model/LoRA/seed/size, or
  openai model/size/quality) via app.write_image_provider_trace - verifying the
  engine that actually rendered, not a configured label.
- tests/render_ab/run_real_ab.py: driver; default engine=local-sd; refuses to run
  unless local_stable_diffusion_status()['ready'] (or, for openai, ENABLE_EXTERNAL_AI
  + key). Captures 3 legacy + 3 Director prompts, renders 6 to sandbox, writes
  manifest.json + report.md (scoring skeleton), exposes failures.
- tests/render_ab/test_harness.py: 10/10 pass. Added LocalSD command-construction
  test (monkeypatched subprocess: asserts identical generator command + LoRA +
  enhanced prompt) and not-ready failure-exposure test. All free/offline.
- No generation fired. No Director/AIVSB/Bible/provider/metadata changes. Slice 2
  not started. AIVSB frozen.

## Verification (this commit, no cost)
10/10 A/B harness tests pass. Plus 5 Slice-1 unit + 5 integration tests pass.

## Next step (run in the SD GPU runtime - no API billing)
  python tests/render_ab/run_real_ab.py --backend local-sd
Renders 6 images (3 legacy SDXL + 3 director SDXL) through the real app pipeline.
Then score each 3-image set 1-5 on the 7 criteria + per-image Liang-recognizable,
compute the gate. A tie is not enough; a prettier isolated image is not enough -
the Director must improve the usable sequence.

## Gate (from directive)
Recommend continue ONLY when ALL:
  - overall_improvement Director > Legacy
  - canon_accuracy Director >= Legacy (no regression)
  - >= 2 of 3 Director images keep recognizable Liang identity
  - three-shot sequence visibly differentiated (shot_differentiation >= 4)
