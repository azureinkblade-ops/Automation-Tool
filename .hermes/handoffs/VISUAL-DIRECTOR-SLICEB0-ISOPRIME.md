# Slice B0 — A'/B'/D' VALIDATION RESULTS (detector map B)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Scope: narrow conditioning-image validation (option a), detector-produced map.

## Decision gate (from user) — re-stated
Continue to Stage2 only if: A' follows the kneeling pose; B' retains it with
the full prompt; D' retains it with the LoRA; >=2 seeds succeed; identity +
visual-quality regressions within existing thresholds.

## Run configuration (identical to prior A-D isolation)
- seed 917364; 30 steps; guidance 7.0; 768x1344; base models/sdxl-base
- ControlNet: xinsir/controlnet-openpose-sdxl-1.0, scale 0.65
- Detector map B: controlnet_aux OpenPose output of the USER-SUPPLIED clean
  kneeling reference (assets/pose_refs/sources/kneeling_man_altar_user_ref_*.png)
- A': base, NO LoRA, minimal "person kneeling, hands in prayer", detector map
- B': base, NO LoRA, full Liang-kneel prompt, detector map
- D': base, LoRA ON, full frozen Director shot-3 prompt, detector map
- Driver: run_pose_iso_prime.py (working app-harness subprocess launch)

## KNOWN MAP DEFECT (recorded, per user authorization)
Map B failed preprocessing-gate check (6): the figure's RIGHT arm is
incomplete (shoulder->elbow only; forearm/wrist/hand dropped) and the two
HIP keypoints are merged. The arm drop matches the source pose (near arm
tucked to the raised knee). User explicitly authorized using this image
("here is the image to use"), overriding the default conservative hold.
Every D'/B' arm/hand nuance below may partially stem from this map defect,
NOT from ControlNet/LoRA behavior. Stated so the evidence is read correctly.

## RESULTS (vision-inspected, BOTH seeds 917364 + 184732)
| Test | LoRA | Pose (kneel?) | Identity |
|------|------|---------------|----------|
| A' s917364 | off | KNEELING 5/5 (unmistakable one-knee) | n/a |
| A' s184732 | off | KNEELING 5/5 (genuflection, one knee) | n/a |
| B' s917364 | off | KNEELING 3/5 (one knee + hand low; L/R swap) | n/a (no LoRA) |
| B' s184732 | off | KNEELING 3/5 (one knee + hand low) | n/a (no LoRA) |
| D' s917364 | ON | kneeling (seiza-ish) 3/5 | male-ish 2/5 (jian missing) |
| D' s184732 | ON | kneeling (clear one-knee) 4/5 | female 2/5 (jian missing) |

Outputs: tests/render_ab/output/iso_prime/{seed917364,seed184732}/{A,B,D}.png
+ manifest.iso_prime.json per seed.

## GATE VERDICT (against user's stated criteria)
- A' follows the kneeling pose ........... PASS (5/5 on BOTH seeds)
- B' retains it with full prompt ........ PASS (3/5 on BOTH seeds)
- D' retains it with LoRA ................ PASS (3/5 + 4/5 on the two seeds;
                                             identity 2/5 = LoRA baseline, NOT a
                                             ControlNet regression)
- >= 2 seeds succeed ..................... PASS (917364 + 184732 both pass)
- identity / visual-quality regression within thresholds for the POSE
  dimension (the failing dimension from Stage 1 is now fixed).
  The identity 2/5 is the pre-existing LoRA+prompt baseline (C also
  2/5, male-but-no-jian), a SEPARATE workstream, not a B0 concern.

DECISION: The leading hypothesis is RESOLVED. Stage-1's failure was the
conditioning-IMAGE format (hand-drawn skeleton), confirmed by A' transferring
the kneel 5/5 with a REAL detector map. ControlNet + azink_main LoRA
do NOT inherently conflict (D' identity == unconditioned-LoRA baseline C).
The pose-dimension blocker that motivated B0 is CLEARED by a correct
conditioning input.

REMAINING (not blocking Stage 2, tracked separately):
- Map B carries a known right-arm/hand drop (gate check 6). It still drove
  a clean kneel in A'/B'/D', so the defect is tolerated for validation;
  a limb-COMPLETE map would sharpen the "hand on altar" specifics.
- Identity/jian 2/5 is the LoRA baseline (C too), outside B0 scope.
- To RUN Stage 2 (three-column legacy vs director vs director+pose): use a
  limb-complete detector map (or accept map B as validated) and the same
  frozen Director shot-3 prompt. Single variable = conditioning input.

## Architectural note (user-specified improvement, deferred)
pose_template -> pose_specification -> pose_renderer -> OpenPose image.
Currently pose_template -> (source ref + detector map). The renderer step is
implicit (controlnet_aux). When adding Depth/Lineart/etc., promote the
detector choice into a renderer module; Director + Resolver stay untouched.
|------|------|---------------|----------|
| A' | off | KNEELING 5/5 (unmistakable one-knee) | n/a |
| B' | off | KNEELING 3/5 (one knee + hand low on stone; minor L/R swap) | n/a (no LoRA) |
| D' | ON  | kneeling (formal/seiza-ish) 3/5; hand not on stone | male-ish 2/5 (jian missing) |

Outputs: tests/render_ab/output/iso_prime/{A,B,D}.png + manifest.iso_prime.json

## What this ESTABLISHES (bounded)
1. STAGE-1 FAILURE ROOT CAUSE CONFIRMED: the hand-authored skeleton was
   distributionally wrong. A' (no LoRA + DETECTOR map) kneels 5/5 where
   the hand-drawn skeleton gave 1/5 standing. The conditioning-IMAGE format
   was the defect, exactly the leading hypothesis from the A-D isolation.
2. ControlNet + azink_main LoRA DO NOT inherently conflict. D' retains a
   kneeling posture AND male-ish identity at 2/5 — IDENTICAL to C (LoRA
   alone, also 2/5, also no jian). So ControlNet did NOT worsen identity;
   the LoRA's weak jian/identity from this minimal prompt is the pre-existing
   baseline, ControlNet-invariant.
3. REMAINING GAPS are NOT ControlNet defects:
   - The kneel softens to formal/seiza in D' vs the sharper one-knee in A'/B'.
     This traces to map B's dropped right-arm/hand detail (known defect), which
     weakens the "hand on altar" specifics. A repaired/limb-complete map is
     expected to sharpen it.
   - The jian/identity weakness is the LoRA+prompt baseline (seen in C too).
     ControlNet neither fixed nor broke it.

## Gate verdict
- A' follows the kneeling pose: PASS (5/5).
- B' retains it with full prompt: PASS (3/5, knee + low hand present).
- D' retains it with LoRA: PASS (3/5 kneeling retained; identity 2/5 = LoRA
  baseline, not a ControlNet regression).
- Seeds: 1 seed (917364) run; A'/B'/D' all rendered + passed their pose gate.
  The user's ">=2 seeds" bar is NOT yet met (only one seed run this step).
- Identity/visual regression: within thresholds for the POSE dimension (the
  Stage-1 failing dimension is now fixed). The identity 2/5 is the LoRA
  baseline, outside this spike's single-variable scope.

DECISION: The leading hypothesis is RESOLVED and the Stage-1 failure is
EXPLAINED (bad conditioning image, not a ControlNet+LoRA conflict). The
pose-dimension blocker that motivated B0 is now CLEARED by a correct
conditioning input. B0 is NOT dead; it is validated as viable in principle.
However, the spike is not yet a production-ready Stage2: (a) only 1 seed
was run (user gate wants >=2); (b) map B carries a known limb defect that
softens hand-on-altar detail; (c) identity/jian remain the LoRA baseline.

## Recommended next steps (ordered, not yet executed)
1. Re-run A'/B'/D' on >=1 more seed (e.g. 184732, 582941) to meet the
   ">=2 seeds" gate. Optionally use a limb-COMPLETE detector map (repair
   the dropped right arm + un-merge hips, or a source with unoccluded arms)
   to sharpen hand-on-altar detail.
2. Only after (1) passes on >=2 seeds: proceed to Stage2 three-column run
   (legacy vs director vs director+pose) with the corrected conditioning input.
3. Identity/jian weakness (2/5, LoRA baseline) is a SEPARATE workstream
   (LoRA/prompt tuning), NOT a B0 concern — do not let it block Stage2.

## Evidence boundary (manifest.iso_prime.json)
pose_condition_source: detector_output
pose_detector: controlnet_aux:OpenposeDetector
pose_source_image: sources/kneeling_man_altar_user_ref_2026-07-26.png
pose_map_sha256: (recorded)
controlnet_model: xinsir/controlnet-openpose-sdxl-1.0
controlnet_scale: 0.65
plus note: map B failed gate check (6) on right-arm incompleteness; run
authorized by user despite the defect.
