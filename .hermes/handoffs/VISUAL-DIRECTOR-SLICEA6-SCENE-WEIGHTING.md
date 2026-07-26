# Handoff: Visual Director Slice A.6 — scene-weighting for interaction shots

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA5-CINEMATOGRAPHY.md
Commit: see git log (visual_director.py only; no test changes needed — all 4
suites green unchanged).

## Why
Run 6 (user review, 8.8-9.0/10) was the FIRST run with a clearly measurable
Director effect: framing/cinematography (Slice A.5) lifted the score and the
control stayed intact (same model/LoRA/scheduler/resolution/negative/seeds).
The user's diagnosis sharpens the bottleneck:
- Camera wording IS working (model obeys it); what it does NOT obey is COMPLEX
  BODY ACTIONS (kneeling, hand-on-stone, formation, staff-vs-jian). That is a
  POSE-GENERATION problem, not a wording/ordering problem.
- "Squeezed most of the value out of prompt sequencing" — stop reordering.
- ONE IMMEDIATE, authorized prompt change: the long environmental inventory
  (mist layers, falling leaves, qi motes, cracked stairs, broken railings,
  roof tiles, banners, dust, hall) is a lot of competing visual objectives. For
  an INTERACTION / RITUAL shot (e.g. Image 3, the formation beat), the narrative
  hinge is the ritual, not the architecture. Reduce the env description to only
  what establishes location, freeing model attention for the pose/interaction.

## Changes (visual_director.py only)
- Added `_INTERACTION_SHOT_TYPES = {"climax","ritual","action","interaction"}`
  and `_ENV_TRIM_TOKENS` (the verbose ambiance inventory words).
- Added `_trim_env_for_interaction(env_state)`: for an interaction/ritual shot,
  drops the long ambiance inventory, keeping only core location-establishing
  descriptors. The location name + architecture remain in the Setting: line, so
  WHERE is still established; the env-state simply stops competing for
  attention with the pose.
- In `_build_shot_plan`, the climactic (ritual) shot now carries the TRIMMED
  env-state; establishing/travel shots keep the full descriptive env-state.
- NO other change: imperative Depict, identity block, jian weapon lock, camera
  framing (Slice A.5), banner removal all UNCHANGED. Prompt semantics frozen.

## Verified (HP Run 6 scene)
- Shot 1 ENV: ancient, mist, mist layers, falling leaves, qi motes, abandoned
  for centuries, partially collapsed, cracked stone stairs, broken jade
  railings, fallen roof tiles, ... (full inventory kept)
- Shot 3 ENV: ancient (trimmed to core location descriptor; ambiance dropped)
- shot3 has no "falling leaves"/"qi motes" (True); shot1 keeps them (True)
- imperative "Depict Liang" retained (True); identity + jian lock retained (True)
- all 4 suites green (unit 5/5, integration 5/5, review 8/8, harness 10/10)

## Out of scope (explicitly deferred — the user's forward roadmap is a
## DIFFERENT LAYER, not prompt text)
1. Pose conditioning (ControlNet / OpenPose / reference-based) — highest-impact
   next step, but a build/integration decision, not a prompt change. NOT done
   here; flagged for a separate slice when the user authorizes the layer.
2. Shot taxonomy (small reusable set: establishing/hero/action/ritual/close-up
   mapping to concise camera instructions) — reduces prompt variability;
   proposed, not implemented this turn (would touch camera + shot-type design).
3. Systematic subject-to-environment balance — partially addressed by Slice A.5
   framing + this trim; full systematization deferred.

Deferred (unchanged from prior slices):
- Weapon regression (staff vs explicit jian): persistent MODEL PRIOR. No more
  weapon wording added. Owners per user: xianxia-swordsman LoRA, reference
  conditioning, or Slice B post-generation correction.
- Slice B (finishing) + Slice C (integration) remain separate gated experiments.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).

## Next
Re-run the controlled A/B on Slice A.6 to confirm the trimmed env helps the
interaction shot (Image 3) without hurting shots 1/2:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Primary metric: Image 3 narrative/pose adherence (was ~7.5) — does freeing
env attention let the kneeling/formation beat land? Watch that shots 1/2 (8.8-9.4)
do not regress from the trim (they keep full env). If pose fidelity still fails
after this, the user's roadmap points to pose conditioning (ControlNet) as the
next layer — a separate build decision. Realistic LoRA track still pending.
