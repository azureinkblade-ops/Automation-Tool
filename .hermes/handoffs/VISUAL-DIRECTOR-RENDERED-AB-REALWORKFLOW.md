# Handoff: Rendered A/B through the REAL application image workflow

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: (run `git rev-parse --short HEAD`)
Parent: `af2fa17` (A/B harness + mocked tests), `5e3e10e` (integration), `d2fae2c`, `93b9241`.

## Correction applied (user-directed)
Earlier I proposed rendering via the standalone Hermes FLUX 2 (FAL) tool. The user
correctly rejected that: it is a SEPARATE code path that never feeds posts/videos,
so it proves nothing about the Visual Director's effect on shipped assets. The A/B
must run through the APPLICATION workflow.

## What the real app workflow actually is
There is NO FLUX 2 / FAL path in app.py. The real image providers are:
  - local_stable_diffusion (diffusers SDXL) - currently UNAVAILABLE (deps missing)
  - openai  -> create_openai_image() -> OpenAI gpt-image-1 (model=OPENAI_IMAGE_MODEL)
  - google_ai -> create_google_ai_image() (Gemini) - but it mutates promo rotation
    state (production metadata), so it is AVOIDED for the A/B to respect the
    "do not touch production metadata" constraint.
  - banked / pexels / pixabay / local_fallback (stock or no character canon)
Provider priority: local_stable_diffusion, openai, google_ai, banked, pexels,
pixabay, local_fallback. In this env openai is READY (OPENAI_API_KEY saved).

## This commit (isolated: orchestration + evaluation only)
- tests/render_ab/harness.py: added OpenAIAppBackend that drives the REAL
  app.create_openai_image for both prompt sets, writes each file to the sandbox
  (legacy/ + visual-director/), and records the REAL provider trace (model/size/
  quality) via app.write_image_provider_trace - so we verify the engine that
  actually rendered, not the configured label (per the directive).
- tests/render_ab/run_real_ab.py: driver. Captures the 3 legacy + 3 Director
  prompts from the production path, renders 6 images through OpenAIAppBackend into
  a sandbox, writes manifest.json + report.md (scoring skeleton), exposes failures.
  GUARDED: refuses to run unless ENABLE_EXTERNAL_AI=1 and OPENAI_API_KEY are set.
  Cost: 6 billed OpenAI image calls. NOT executed in this commit.
- tests/render_ab/test_harness.py: added RecordedBackend test (real traces flow
  through run_ab) without network/cost. Total 8/8 harness tests pass.
- No generation fired. No Director/AIVSB/Bible/provider/metadata changes. Slice 2
  not started. AIVSB frozen.

## Verification (this commit, no cost)
8/8 A/B harness tests pass (capture, 6-image run, recorded-backend real traces,
manifest+report, gate tie/regression/win, sandbox isolation). Plus 5 Slice-1
unit + 5 integration tests pass.

## Next step (needs EXPLICIT cost authorization - per user directive)
Run:  ENABLE_EXTERNAL_AI=1 OPENAI_API_KEY=<real> VISUAL_DIRECTOR_ENABLED unset \
       python tests/render_ab/run_real_ab.py
This bills 6 OpenAI images (3 legacy gpt-image-1 + 3 director gpt-image-1) through
the same app code the posts/videos use. Then score each 3-image set 1-5 on the 7
criteria + per-image Liang-recognizable, apply the gate. A tie is not enough; a
prettier isolated image is not enough - the Director must improve the usable
sequence. Confirm OpenAI billing is acceptable before I run it.
