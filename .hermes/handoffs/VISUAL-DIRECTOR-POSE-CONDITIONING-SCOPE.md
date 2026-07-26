# Scope: Visual Director — Pose-Conditioning Build (Slice B0, PARALLEL ISOLATED)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Trigger: User chose option C at the prompt-phase plateau (Run 8): freeze the
Director, scope the pose-conditioning build as a parallel isolated slice while
Slice B (finishing) / Slice C (integration) proceeds.

STATUS: SCOPE ONLY. No build performed. This document defines the slice, the
current backend reality (verified), the work items, the risk profile, and the
gates. Building requires a SEPARATE authorization + model-download approval.

## Why this is a build, not a prompt edit (verified reality)
The Director prompt phase is frozen at 691e22a. Remaining gap: Action fidelity
7.2/10, Pose fidelity 6.8/10. Run 8 proved better prompts != better composition.

Backend recon (read, not assumed):
- app.py:7604 `create_local_stable_diffusion_image` shells out to a generator
  script via subprocess. Args passed: --prompt, --negative-prompt, --model,
  --refiner-model, --quality-mode, --scheduler, --width/--height, --steps,
  --guidance-scale, --seed, --metadata, [--lora-path, --lora-scale],
  [--input-image, --strength]. NO controlnet/openpose arg.
- local_image_generator.py (292 lines): uses diffusers AutoPipelineForText2Image
  / AutoPipelineForImage2Image. Scheduler is swappable (DPM/Euler/DDIM). NO
  ControlNet, NO OpenPose/DWpose, NO IP-Adapter, NO reference-image conditioning
  anywhere in the repo (verified by search across .py/.json: 0 hits).
- Therefore pose conditioning requires NEW backend infrastructure. Not present.

## Goal
Constrain character BODY POSITION (kneeling, hand-on-stone, formation) so SDXL
obeys the pose instead of defaulting to standing. Target the two failing axes:
pose fidelity (kneeling/upright) and interaction (hand placement, formation
floor) for the climactic/interaction shots.

## Approach options (pick one at build time)
A. ControlNet (OpenPose/skeleton): generate a pose-reference image per shot
   (skeleton stick-figure matching the Director's Pose: spec) and feed it as a
   ControlNet conditioning image at low-moderate strength.
   - Pros: most direct control over body position.
   - Cons: needs a SDXL-compatible pose ControlNet model (download + VRAM);
     requires generating/authoring the pose-reference image per shot.
B. Reference-based composition (IP-Adapter / T2I-Adapter pose): condition on a
   reference pose image. Similar infra cost.
C. DWpose/OpenPose runtime estimation: estimate pose from a hand-authored
   reference render. Adds an inference step.
Recommendation for first attempt: A with a hand-authored pose-reference image
per shot type (no runtime pose-estimation needed) — lowest moving parts, fully
reproducible under the controlled A/B methodology.

## Work items (isolated slice, env-gated, default OFF)
1. Generator: add ControlNet support to local_image_generator.py
   - new args: --controlnet-image PATH, --controlnet-scale FLOAT, --controlnet-model PATH
   - load SDXL ControlNet (diffusers ControlNetModel + StableDiffusionXLControlNetPipeline
     or attach controlnet to the existing pipe), feed conditioning image + scale.
   - Must NOT alter the existing txt2img/img2img path when args absent (backward
     compatible; legacy A/B still valid).
2. App wiring: create_local_stable_diffusion_image gains optional
   controlnet_image / controlnet_scale / controlnet_model params, passed through
   only when provided. Director integration passes them only when the new flag
   VISUAL_DIRECTOR_POSE_CONDITIONING=1 (env-gated, default OFF).
3. Pose-reference artifact: Visual Director emits, per interaction/pose-critical
   shot, a pose spec (from its Pose: field) -> a small skeleton reference PNG
   authored in-repo (e.g. assets/pose_refs/climax_kneel_altar.png). Stored as a
   deterministic asset, not generated at runtime (reproducible).
4. Controlled A/B harness extension: add a third column "director+pose" using
   the SAME seeds (184732/582941/917364) so the ONLY change vs the frozen Director
   is the ControlNet conditioning. Keep legacy + frozen-Director columns intact.
5. Negative prompt: keep jian lock / no-staff behavior; pose conditioning does
   not change weapon handling.

## Risk profile (separate from prompt phase)
- VRAM: ControlNet + SDXL LoRA + base may exceed current GPU budget. Must verify
  on the SD GPU runtime before activation.
- Model download: a pose ControlNet checkpoint must be fetched (external asset).
  REQUIRES explicit user cost/availability approval (paid/external fetch).
- New failure modes: distorted anatomy from over-weighted ControlNet; pose-ref
  asset must match LoRA character proportions.
- Reproducibility: ControlNet adds a conditioning input; the controlled A/B must
  still isolate it as the single variable.

## Gates (before any activation / merge)
- G1: generator runs with --controlnet-image and produces a valid image WITHOUT
     breaking the no-arg path (regression check on legacy + frozen Director).
- G2: controlled A/B shows Action fidelity and Pose fidelity IMPROVE vs frozen
     Director (target: pose 6.8 -> >=8.5, action 7.2 -> >=8.5) WITHOUT Identity
     (9.2) or Environment (9.8) regressing.
- G3: VRAM verified on SD GPU runtime; no OOM.
- G4: env-gated OFF by default; production path unchanged until adoption decision.

## Out of scope (this slice)
- Slice B finishing (inpaint/upscale/face-fix) and Slice C integration: proceed
  independently per the original plan.
- Weapon-prior fix (staff vs jian) is a model-prior; pose conditioning may help
  marginally but is not its primary target.
- Any change to the frozen Director prompt architecture (691e22a).

## Decision needed from user to proceed to BUILD
1. Approve the build slice (option A recommended as first attempt).
2. Approve fetching a SDXL pose ControlNet checkpoint (external asset; cost/
   source confirmation).
3. Confirm env-gated default-OFF + separate seed-paired A/B column approach.
