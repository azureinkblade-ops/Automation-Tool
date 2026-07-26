# Handoff: Visual Director Slice A.5 — cinematography / framing

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA4-IMPERATIVE-SCENE.md
Commit: see git log (visual_director.py only; no test changes needed — all 4
suites green unchanged).

## Why
Run 5 (user review, ~7.6-7.8/10) was essentially NO improvement over Run 4.
Crucially, it RULED OUT a hypothesis: replacing the labeled "Narrative
Objective:" / "Action:" with a single "Depict Liang ..." imperative barely
moved the needle (Action fidelity stayed low, shot 3 still produced a standing
ceremonial-staff "priestess" instead of the kneeling jian user). Control
remained valid (manifest: same checkpoint/LoRA/scheduler/seed/resolution/
negative per pair; prompt is the only variable).

User's diagnosis: the bottleneck is COMPOSITION, not wording. All three prompts
ask SDXL to satisfy two competing goals (enormous cinematic environment +
detailed human action); the model consistently prioritizes the environment
because that is what it was trained to do ("beautiful architectural
illustrations"). The recurring camera language ("wide low-angle environmental
shot") actively demotes Liang to a speck.

User's directive (approved): FREEZE prompt semantics (identity block,
imperative Depict, environment block, weapon lock all unchanged). Change ONLY
camera framing to keep Liang visually PROMINENT while retaining environmental
context. Continue the same controlled A/B methodology to isolate the framing
effect. Do NOT add more weapon text (the staff is a persistent MODEL PRIOR, not
a prompt deficiency — Slice B / reference conditioning owns that).

## Changes (visual_director.py only)
- Replaced the three `cameras` strings. No other field (semantic content,
  order, identity lock, weapon lock, environment block, banner removal) changed.
  - Shot 1: "full-body medium shot of Liang entering the ruined sect hall; Liang
    occupies roughly one third of the frame while the towering ruined sect hall
    and gateway fill the background"  (was "wide low-angle environmental shot").
  - Shot 2: "over-the-shoulder tracking shot from behind Liang as he climbs the
    broken stair; Liang remains clearly visible and prominent in the lower
    third of the frame with the jade altar rising ahead".
  - Shot 3: "three-quarter side view from altar height, Liang clearly the
    subject kneeling on one knee before the altar with the dormant formation
    glowing on the floor behind him".
- The framing injects an explicit relative-size cue ("roughly one third of the
  frame", "prominent in the lower third") so the model weights the subject over
  the environment, per the user's "communicate relative visual importance"
  instruction. Environmental context is explicitly retained in every shot.

## Verified
- old "wide low-angle environmental shot" absent (True)
- imperative "Depict Liang" retained (True)
- identity block + jian weapon lock retained (True)
- "one third of the frame" framing present (True)
- all 4 suites green (unit 5/5, integration 5/5, review 8/8, harness 10/10)

## Tests
No test changes required; all green unchanged.

## Deferred (unchanged from prior slices)
- Weapon regression (staff despite explicit jian): classified by user as a
  persistent MODEL PRIOR. No more weapon wording added. Owners: (a) a
  xianxia-swordsman-trained model/LoRA, (b) reference-based conditioning
  (ControlNet/IP-Adapter), or (c) post-generation correction (Slice B).
- Slice B (finishing: inpaint/upscale/face-fix) + Slice C (automation
  integration) remain separate gated experiments.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).

## Next
Re-run the controlled A/B on Slice A.5 to isolate the framing effect:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Primary metric: Liang's on-screen PROMINENCE / character scale (was a speck in
shots 1-2) and whether action readability improves now that he is framed larger,
without losing the environment quality gains. Story/Action fidelity should rise
if composition was the suppressor. Realistic LoRA track still pending (user
asked both main-posts + realistic).
