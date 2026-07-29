# Slice B0 Stage 1 — POSE-CONDITIONING VIABILITY SPIKE: RESULT

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Checkpoint: xinsir/controlnet-openpose-sdxl-1.0 (downloaded ~5GB free local to
  C:\Users\David\Documents\Automation tool\models\controlnet-openpose-sdxl-1.0)
Scope: single failing frame (shot 3, climax) only. Frozen Director prompt, same
  seed/model/LoRA/dimensions/steps/guidance. Variable = ControlNet conditioning.

## Verdict (precise)
The CURRENT B0 implementation FAILED its Stage 1 acceptance gates.
This is a statement about this integration (checkpoint + my hand-authored pose
image + this pipeline wiring + azink_main LoRA at 0.75). It is NOT yet a proof
that pose conditioning per se is infeasible. The remaining work is to find the
correct conditioning strategy; ~80-90% of the engineering (plumbing, CLI, app
wiring, pose registry, harness, tests) is done and reusable.

## What was built (slice scaffold, committed separately, env-gated OFF)
- local_image_generator.py: native StableDiffusionXLControlNetPipeline path,
  5 new CLI args (--controlnet-model/image/scale/--control-guidance-start/end),
  backward-compatible (no-arg path unchanged).
- pose_resolver.py: Pose Resolver -> template ID -> asset PNG (Director picks the
  TEMPLATE, does not draw; honors the user's responsibility split).
- assets/pose_refs/climax_kneel_touch_altar_v1.png: hand-authored OpenPose-style
  skeleton (kneel on one knee, one hand low to altar).
- app.create_local_stable_diffusion_image: optional controlnet_* params, env-gated.
- harness + run_real_ab + run_pose_stage1.py: third 'director+pose' column + driver.
- 6 GPU-free unit tests (resolver + command construction) all pass.

## Stage 1 evidence — OBSERVED facts (6 ControlNet renders inspected)
Rendered 3 seeds x scale 0.65, plus scales 0.45/0.85 on seed 917364.
All 5 inspected ControlNet images FAILED both required gates:

| render | pose (kneel?) | identity (male Liang + jian?) |
|--------|---------------|-------------------------------|
| seed184732 @0.65 | standing, female, red gourd | FAIL |
| seed582941 @0.65 | standing, female, red tassel | FAIL |
| seed917364 @0.65 | standing, female, red tassel  | FAIL |
| seed917364 @0.45 | standing, female, staff      | FAIL |
| seed917364 @0.85 | sitting on steps, female     | FAIL |

OBSERVED (objective):
- The pipeline executed successfully; no crash; VRAM sufficient (6/6 rendered
  across 3 seeds; 3/3 seed-level successes on the rendering-reliability gate).
- The resulting images failed the acceptance criteria (pose + identity).
- The failures were reproducible across multiple seeds and across scales 0.45/0.65/0.85.
- Generator metadata confirms the LoRA WAS loaded in the ControlNet path
  (loraLoaded=True, scale 0.75, same azink_main path as the unconditioned run).
  So ControlNet did NOT silently drop the LoRA.
- The identity regression is scale-independent: at the weakest influence (0.45) the
  image is STILL a standing female with a staff, no jian, no kneel. If the
  problem were purely "ControlNet too strong," 0.45 would have recovered
  identity. It did not.

## Root-cause attribution — HYPOTHESES, NOT conclusions
The evidence shows the current integration regresses identity and does not transfer
the kneel. It does NOT uniquely identify the cause. Equally plausible candidates:

1. Improperly formatted conditioning image. The biggest unknown. I hand-authored
   an OpenPose-style skeleton; most OpenPose ControlNet checkpoints are trained on
   DETECTOR output (DWPose/OpenPose), which has precise keypoint locations, exact
   colors (face red, body white, hands/feet red), exact limb ordering, and
   confidence assumptions. A hand-drawn skeleton can look valid while being
   distributionally different from what the network learned -> it may be ignored
   or misread. This is the SIMPLEST hypothesis and the first to test.
2. Pipeline/configuration error (wrong variant, scheduler interaction, prompt
   ordering, checkpoint mismatch with this base model).
3. ControlNet loaded but not influencing as intended (too weak to matter) OR
   influencing far more than intended (overriding identity).
4. A genuine ControlNet-char-LoRA interaction where the conditioning signal and
   the LoRA compete for the person token. POSSIBLE but NOT established by the
   evidence; do not state as fact.

The original draft overstated (4) as "the known SDXL ControlNet + character LoRA
conflict." That goes beyond the evidence. Correct statement: "The current
integration exhibits identity regression when using this ControlNet configuration."

## Next experiment (authorised as a debugging session, not a prompt tweak)
Pipeline validation to isolate the variable (seed 917364, 30 steps, guidance 7.0,
768x1344, same base model, across all four):

  A: base SDXL, NO LoRA, minimal prompt "standing person", pose image
     Q: does the POSE actually transfer (kneel) with no LoRA to interfere?
  B: base SDXL, NO LoRA, Liang-kneel prompt, pose image
     Q: does kneeling happen when prompt asks + pose image present?
  C: base SDXL, LoRA, NO ControlNet   -> identity check (should be Liang)
  D: base SDXL, LoRA, ControlNet        -> exactly where does identity disappear?

Driver: tests/render_ab/run_pose_iso.py (reuses the WORKING Stage 1 subprocess
launch; the generator's torch import only succeeds when launched via the app
harness, not as a bare CLI call — see OBSERVED caveat below). Outputs under
tests/render_ab/output/iso/{A,B,C,D}.png.

If A/B show NO pose transfer, the conditioning image format is the culprit (fix:
render via a real DWPose/OpenPose detector, or author a canonical colored skeleton).
If C is correct-Liang but D regresses, the LoRA/ControlNet interaction is the
culprit (fix: condition without touching the person token, e.g. depth/canny
composition controlnet, or load ControlNet post-LoRA-identity).

## Architectural improvement (for the next iteration, not yet implemented)
Evolve:
    pose_template -> PNG (current)
to:
    pose_template -> pose specification -> pose renderer -> conditioning image
so the Director ALWAYS emits semantic intent, and only the renderer changes when
we support OpenPose / Depth / Lineart / Scribble / Canny / Segmentation. The
Director and Pose Resolver stay untouched.

## What is preserved
- Director prompt architecture frozen at 691e22a (unchanged, still production-valid).
- Slice B0 scaffold committed, env-gated OFF; production image path byte-identical.
- ControlNet default OFF.

## Decision status
Do NOT proceed to Stage 2 three-column run until the A-D isolation identifies the
cause and a fix is validated. Slice B (finishing) and Slice C (integration)
remain the originally-scoped next phases and do not depend on solving pose.
Close-or-iterate B0 only after the isolation experiment.

## OBSERVED caveat (environment)
A bare call `.venv-gpu/Scripts/python.exe local_image_generator.py ...` fails to
import torch (OSError: torch_python.dll not found). The SAME generator succeeds
when launched as a subprocess from within app (local_stable_diffusion_status ->
app import -> harness render). So all isolation renders MUST go through
run_pose_iso.py / run_pose_stage1.py (app-harness launch), never a bare CLI call.
Root of the DLL-path difference is not yet diagnosed; treat it as the supported
launch path, not a bug to fix now.
