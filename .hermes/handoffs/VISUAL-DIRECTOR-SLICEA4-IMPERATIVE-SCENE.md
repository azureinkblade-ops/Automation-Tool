# Handoff: Visual Director Slice A.4 — imperative scene description

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA3-ACTION-FIRST.md
Commit: see git log (visual_director.py + 2 test files; tests only relabeled
the per-shot-distinctiveness assertion from "Narrative Objective:" to "Depict").

## Why
Run 4 (user review, ~7.8/10) was a MIXED result: aesthetically stronger
(Composition 8.5->9.0) but narratively weaker. Action fidelity FELL 7.5->5.5
and Story accuracy 8.0->6.5. Critically, Run 4 shot 3 regressed hardest:
requested kneel/altar/silver-qi/formation; got a standing hero holding a
ceremonial STAFF (the model substituted a mage archetype despite the explicit
jian lock). Control remained valid (manifest: only prompt differed; model,
LoRA, scheduler, seed, size, negative all matched per pair).

User's diagnosis: ordering experiments have hit diminishing returns. SDXL
treats the labeled "Narrative Objective:" / "Action:" headings as DESCRIPTIVE
PROSE, not hard constraints — the labels dilute the event signal. The fix is
STRUCTURAL, not positional.

User's directive (approved): keep the architecture, identity lock, environment
block; REPLACE the labeled Narrative Objective + Action with ONE concise
imperative scene description that encodes the visible event, e.g.
  "Depict Liang kneeling on one knee before the jade altar with his left hand
   touching the stone as silver qi activates the dormant formation."
Then follow with the supporting details (setting, character, camera, lighting…).
Explicitly NOT pursued: more adjectives, longer environment blocks, more weapon
wording, stronger lighting. Re-run same controlled seeds.

## Changes (visual_director.py)
- `_assemble_image_prompts` loop: the two labeled lines
  `Narrative Objective:` and `Action:` are replaced by a single
  `_imperative_scene(shot, name)` output. Order of the REMAINING fields is
  unchanged: Setting -> Environment State -> Character Identity -> Camera ->
  Lighting -> Power -> Emotion -> Palette -> Consistency.
- New helper `_imperative_scene(shot, name)`: composes
  `Depict <Name> <action>, as <objective>.` when the objective adds context the
  action lacks, else `Depict <Name> <action>.`. The character NAME is bound to
  the (subjectless) action phrase so the event reads as "Depict Liang …" and
  SDXL binds the action to the protagonist — matching the user's example shape
  exactly. If only an objective exists (no action), falls back to
  `Depict <objective>.`
- Identity block, weapon lock, environment block, banner removal (Slice A.3)
  all UNCHANGED.

## Verified prompt lead (HP Run 4 scene)
  [1] Depict Liang standing at the entrance, head tilted upward, looking at the
      ancient formations above the gateway, as Liang enters the ruined sect hall
  [2] Depict Liang midway up the broken staircase, one foot planted on a higher
      step, body leaning forward, robe trailing behind him, right hand hovering
      over the sword hilt, as He climbs the broken stair toward the jade altar
  [3] Depict Liang kneeling on one knee before the altar, left hand pressed to
      the cold stone, silver qi visibly flowing through the dormant formation
      lines on the floor, as Silver light wakes the dormant formation
Checks: no "Narrative Objective:" label, no "Action:" label, "Depict" present,
shot 3 matches the user's example shape verbatim (subject bound), identity
block + jian lock preserved.

## Tests
unit 5/5, integration 5/5, review 8/8, harness 10/10. The integration + harness
assertions were relabeled from the removed "Narrative Objective:" marker to
"Depict" (the new per-shot-distinctiveness anchor); no logic change.

## Deferred
- Weapon regression (shot-3 staff) is MODEL PRIOR overriding an explicit jian
  lock — not a prompt-omission problem; per user instruction, no more weapon
  wording added. Slice B (post-generation inpaint/face-fix) is the correct
  owner.
- Slice B (finishing) + Slice C (automation integration) remain separate gated
  experiments.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).

## Next
Re-run the controlled A/B on Slice A.4 to confirm action + story accuracy
recover without identity/environment regression:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Primary metric to watch: Action fidelity (was 5.5) and Story accuracy (was 6.5)
should rise; Character consistency (8.5) and Environment fidelity (7.5) should
hold. Realistic LoRA track still pending (user asked both main-posts + realistic).
