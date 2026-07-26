# Handoff: Visual Director Slice A.7 — size rule + Pose/Expression split + selective trim

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA6-SCENE-WEIGHTING.md
Commit: see git log (visual_director.py + tests/review_visual_director_slice1.py
review ceiling 1200->1300 with justification; all 4 suites green).

## Why
Run 7 (user review, 9.1/10) confirmed the env-trim (Slice A.6) lifted Image 3
narrative ~7.5->8.7 by freeing model attention from the environment to the
character+pose. The user's review states text-only prompting has now hit
DIMINISHING RETURNS: the residual failures (body pose, exact hand placement,
kneeling-vs-standing, staff-vs-jian) are a MODEL LIMITATION, not prompt
ambiguity. Four optimizations were proposed; this slice implements the
SAME-LAYER, prompt-construction ones and explicitly REJECTS the one the user's
own earlier evidence disproved.

## Changes implemented (visual_director.py)
1. CHARACTER-SIZE RULE (user opt #1): replaced the vague "roughly one third of
   the frame" with an explicit, evaluable rule in all three camera strings:
   "Liang fills approximately 20 to 25 percent of the frame height and is
   immediately recognizable even at thumbnail size". This matches the user's
   exact suggested phrasing and is tunable/measurable.
2. POSE / EXPRESSION SPLIT (user opt #3): the combined body+emotion blob is now
   two independent fields. `Pose:` carries the body mechanics (from poses[i]);
   `Expression:` carries the face/emotion (new `expressions` list: quiet awe /
   determined focus / solemn discovery). Each constraint is now separately
   explicit and tunable. The old `Emotion:` label is removed.
3. SELECTIVE ENV TRIM EXTENDED (user opt #4): the Slice A.6 trim now applies to
   `travel` shots as well as `climax`/ritual/action (Run 7: "apply the same
   principle selectively to other scene types"). `establishing` KEEPS the full
   descriptive env-state because its job is to sell the location (score 9.5 on
   that richness). So: establishing = full env; travel + climax = trimmed env.

## Explicitly REJECTED (user opt #2: action-first reorder)
The user listed an EXPERIMENT: ACTION/POSE/HANDS/CAMERA/CHARACTER/SETTING/...
ahead of descriptive context. BUT the user also said "stop spending significant
effort on general prompt wording" and earlier runs PROVED reordering hurts:
Slice A.3 put Action immediately after Objective and action fidelity FELL
7.5->5.5 (Run 4). So the action-first reorder is rejected by the user's own
prior evidence. NOT applied. The current order (imperative Depict -> Setting ->
EnvState -> Character -> Camera -> Pose -> Expression -> Lighting -> Power ->
Palette -> Consistency) stands.

## Deferred (the user's stated NEXT LAYER — not prompt text)
- Pose conditioning (ControlNet / OpenPose / reference-based composition): the
  user identifies this as the highest-impact next step for pose fidelity, but
  it is a SEPARATE BUILD/INTEGRATION decision (new dependency, different layer).
  NOT built this turn. Flagged for a separate slice when the user authorizes it.
- Shot taxonomy (reusable establishing/hero/action/ritual/close-up set):
  proposed by user, not implemented this turn.
- Weapon regression (staff vs explicit jian): persistent MODEL PRIOR. No more
  weapon text added (per user). Owners: xianxia-swordsman LoRA, reference
  conditioning, or Slice B post-generation correction.
- Slice B (finishing) + Slice C (integration) remain separate gated experiments.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).

## Verified (HP Run 7 scene)
- all 3 camera strings carry "20 to 25 percent of the frame height" (True)
- Pose: + Expression: fields present in all 3 (True); Emotion: label gone (True)
- establishing (shot1) keeps full env ("falling leaves" present); travel (shot2)
  + climax (shot3) trimmed ("falling leaves" absent) (True)
- imperative Depict + identity block + jian weapon lock retained (True)
- prompt lengths: shot1=1250, shot2=1143, shot3=1142 chars -> review ceiling
  raised 1200->1300 with justification (precision, not padding).
- all 4 suites green (unit 5/5, integration 5/5, review 8/8, harness 10/10)

## Next
Re-run the controlled A/B on Slice A.7:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Metrics: (a) character scale now ~20-25% (was 10-15%); (b) Image 3 pose
adherence holds/improves with the Pose/Expression split; (c) shots 1/2 don't
regress (shot1 keeps full env). If pose fidelity STILL fails after this, the
user's roadmap is explicit: move to pose conditioning (ControlNet) — a separate
layer/build decision. Realistic LoRA track still pending (user asked both
main-posts + realistic).
