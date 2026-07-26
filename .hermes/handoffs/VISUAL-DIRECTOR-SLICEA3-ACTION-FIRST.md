# Handoff: Visual Director Slice A.3 — action-first reorder + banner removal

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA2-FIELD-HYGIENE.md
Commit: see git log (visual_director.py only; tests unchanged, all green).

## Why
Run 3 (user review, ~8.5/10) confirmed identity consistency is SOLVED and the
sword is now a believable jian in shots 0/1. Two failure modes remain, both
prompt-weighting (not architecture, not new fields):
- ACTION FIDELITY is the weakest category. Run 3 shot 3 requested
  kneel/altar/silver-qi/dormant-formation; the model produced a standing hero
  portrait and ignored the event entirely.
- ENVIRONMENT DRIFT. Run 3 shots 0 and 2 drifted outdoors (mountain stream /
  outdoor mountain) despite the ruined-hall requirement — the character
  description outweighed the scene.
- BANNER PSEUDO-TEXT. Even with "no writing, no symbols, no calligraphy", SDXL
  hallucinated pseudo-Chinese calligraphy on banners. Model habit; user ruled
  not worth fighting in-prompt.

User directive (approved): reorder the EXISTING fields to
  Narrative Objective -> Action -> Setting -> Environment State ->
  Character Identity -> Camera -> Lighting -> Power -> Emotion -> Palette ->
  Consistency instruction
Rationale: Action immediately after Objective gives the event the strongest
available position without changing the renderer or adding bulk; Setting +
EnvState outrank Character so the scene anchor beats identity drift. Remove
banners from the positive prompt (global negative already discourages text; a
positive banner cue gives SDXL a surface to invent pseudo-calligraphy). Keep
identity + weapon lock. Add no new fields. Re-run same seeds. REJECT the change
if identity regresses while action/env improve.

## Changes (visual_director.py only)
- `_assemble_image_prompts` loop reordered to the approved sequence. Action
  sits at position 2 (right after Objective); Setting + Environment State at 3/4
  (ahead of Character at 5). No field content changed.
- Banner phrase removed from the positive prompt. The location architecture's
  'red banners' token is still stripped from env_line (avoids a bare "red
  banners" leak) but no banner text is emitted. The `banner_line` shot field is
  computed but no longer consumed (harmless; left in the shot-dict contract).
- Identity block and weapon lock (`one standard-length Chinese jian…`) and
  negative-prompt spear/staff/polearm exclusions are UNCHANGED.

## Verified prompt order (HP Run 3 scene)
Narrative Objective -> Action -> Setting -> Environment State -> Character
Identity -> Camera -> Lighting -> Power -> Emotion -> Palette -> Consistency.
Checks: Action before Character (T), Setting before Character (T), EnvState
before Character (T), Objective before Action (T), banner phrase absent (T),
'red banners' absent (T), weapon lock kept (T), identity block kept (T).

## Tests
unit 5/5, integration 5/5, review 8/8, harness 10/10 (none required changes;
assertions are order-independent).

## Deferred
- Weapon regression in shot 2 (oversized ceremonial sword) is MODEL BIAS, not
  prompt omission — the lock is already maximal. Per user instruction, NO more
  weapon wording added. This is exactly Slice B (post-generation inpaint/face-
  fix) territory.
- Slice B (finishing pipeline) and Slice C (automation integration) remain
  separate gated experiments.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).

## Next
Re-run the controlled A/B on Slice A.3 to confirm action + environment
adherence improved WITHOUT identity regression:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Reject criterion: if identity consistency regresses while action/env improve,
revert this commit. Realistic LoRA track still pending (user asked both
main-posts + realistic).
