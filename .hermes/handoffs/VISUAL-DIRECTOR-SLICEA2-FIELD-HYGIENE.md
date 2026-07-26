# Handoff: Visual Director Slice A.2 — field hygiene + action compliance

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA-REFINEMENT.md, VISUAL-DIRECTOR-RENDERED-AB-RUN2-SLICEA.md
Commit: see git log (visual_director.py + 3 test files; tests/ folder only).

## Why
Run 2 (Run 2 handoff) confirmed the Director still beats legacy and Slice A
removed the gender flip + repetition. The user's Run 2 review then named six
narrow, prompt-level defects (all Director-construction, NOT Slice B):
1. env "ordered" contradicts "ruined" -> SDXL draws intact temples
2. Director 1 shows standing, not climbing (weak pose verb)
3. Director 2 shows standing hero, not kneeling (camera biased upright)
4. weapon drifts to staff/polearm (loose "silver-edged sword")
5. banner text artifacts (positive banner cue beats global text-negative)
6. "red banners nearby" leaked into the Character Identity block (contamination
   -> robe-color mixing -> the red robe in Director 1)
Plus image-level scores: Character 9, Gender 9, Costume 7, Environment 6,
Narrative 7, Action 5, Mobile 9, Overall 8.

## Changes (all in visual_director.py, env-gated, no provider/metadata change)
- #6 Field hygiene: `_character_lock_tokens` now SKIPS scene-placement tokens
  (banners/nearby/around) so they never enter the Character Identity block;
  they are emitted under Setting instead. Identity block now carries ONLY
  persistent identity (name/gender/age/build/hair/eyes/robe/weapon).
- #4 Weapon lock: replaced the loose "silver-edged sword" with one exact
  phrase: "one standard-length Chinese jian, straight double-edged blade,
  simple silver guard, sheathed at his left hip" (appended to the identity
  block; any loose Bible weapon word is stripped first). Negative prompt now
  force-excludes "spear, staff, polearm, oversized weapon, no spear/staff/polearm".
- #1 Environment state: added _RUIN_CONTRADICTORY = {ordered, pristine, intact,
  maintained, well kept, polished}. The frozen Bible's damage_state "ancient,
  ordered" is token-stripped so "ordered" cannot contradict a ruined scene;
  when the scene/location implies ruin, concrete ruin language is injected
  ("abandoned for centuries, partially collapsed, cracked stone stairs, ...").
- #2/#3 Action + camera agreement: poses rewritten with STRONG bodily
  mechanics (climbing = "midway up the broken staircase, one foot planted on a
  higher step, body leaning forward, robe trailing, right hand over hilt";
  kneeling = "kneeling on one knee, left hand pressed to stone, silver qi
  flowing through dormant lines"). Camera for the climax changed from
  "low-angle hero shot" (biased upright) to "three-quarter side view from altar
  height, Liang visibly kneeling on one knee" so pose and camera agree.
- #5 Banners: emitted under Setting as "plain weathered red cloth banners, no
  writing, no symbols, no calligraphy" (one clean phrase; raw tokens like
  "red banners nearby" and the location architecture's "red banners" are
  stripped so no pseudo-text cue leaks).

## Tests
- unit 5/5, integration 5/5, review 8/8 (ceiling raised 600->1200 with
  justification: Slice A.2 added precision fields the user explicitly requested;
  prompts ~860-1130 chars, still structured/art-directed, SDXL consumes 1000+
  char prompts fine), harness 10/10.
- One real bug found + fixed during verification: test assertions checked
  "Chinese jian" (capital C) against a lowercased blob -> case mismatch. Fixed
  to "chinese jian". (Not a prompt defect; a test-only casing bug.)

## Verified prompt (HP, Run 2 scene)
Identity: Name: Liang; Gender: male; Age: young adult; Appearance: dark
topknot hair, calm eyes, cultivator lean, jade sect robes; Weapon: one
standard-length Chinese jian, straight double-edged blade, simple silver guard,
sheathed at his left hip.
Setting: Mountain sect courtyard, jade hall, plain weathered red cloth banners,
no writing, no symbols, no calligraphy.
Environment State: ancient, mist, mist layers, falling leaves, qi motes,
abandoned for centuries, partially collapsed, cracked stone stairs, broken jade
railings, fallen roof tiles, faded and torn banners, dust and mist inside the hall.
Climax Camera: three-quarter side view from altar height, Liang visibly
kneeling on one knee.
No "red banners nearby" in Identity. No "ordered". No pseudo-text banner cues.

## Deferred (still Slice B, separate experiment)
The remaining Run 2 defects are SDXL+LoRA FIDELITY limits the post-generation
finishing pipeline addresses: occasional weapon/costume/face drift, generated
pseudo-text on surfaces other than banners, exact pose compliance still partly
suggestion-driven. Slice B (img2img/inpaint/upscale/face-fix) is a SEPARATE
gated experiment per the phased plan.

## Next
Re-run the controlled A/B on the Slice A.2 Director to confirm the hygiene
changes improve the image-level scores (esp. Costume 7->?, Environment 6->?,
Action 5->?, and kill banner pseudo-text) without regression:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
Then scope Slice B from the new residual defects. Realistic LoRA track still
pending (user asked both main-posts + realistic).
