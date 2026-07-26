# Handoff: Visual Director — END OF PROMPT-REFINEMENT PHASE (plateau reached)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-SLICEA7-SIZE-POSE-EXPR.md
Status: NO CODE CHANGE this turn. visual_director.py frozen at 691e22a (Slice A.7).
This is a phase-boundary / plateau assessment, not a slice.

## Run 8 review (user, 2026-07-26)
Control matched across A/B (same SDXL/LoRA/scheduler/resolution/negative/seeds).
Director prompts objectively tightened (explicit 20-25% occupancy, Pose/Expression
split, selective env trim). Rendered result: MIXED, not uniform improvement.
- Image 1 (entrance): 9.5 -> 9.7. Larger Liang target worked; reads as protagonist
  anchor. Minor: foreground NPCs compete slightly (user prefers fallen statues /
  broken guardian beasts / damaged sect markers over random cultivators).
- Image 2 (staircase): 8.6 -> 8.4 (slight regression). Prompt better, image didn't.
  Model still chose architecture over action; red sword/banner on left steals
  attention from Liang. Confirms prompt is no longer the limiting factor.
- Image 3 (formation): stable ~8.8-9.0. Cleaner env/lighting/framing, BUT pose
  still NOT obeyed (prompt kneeling/hand-on-stone -> image standing/upright;
  formation floor -> glowing doorway).

## Decisive conclusion (user)
"Better prompts != guaranteed better compositions." The bottleneck has moved from
LANGUAGE to GENERATION. Treat this as the END of the prompt-refinement phase.
Remaining weaknesses (Action fidelity 7.2/10, Pose fidelity 6.8/10) are
concentrated in areas text prompts alone cannot control.

## Maturity assessment captured (user, Run 8)
Canon fidelity 10/10 | Environment selection 9.8 | Lighting 9.7 | Composition 9.3
| Character consistency 9.2 | Story readability 9.1 | Action fidelity 7.2
| Pose fidelity 6.8

## Four user suggestions -> mapped by evidence
1. Shot taxonomy (reusable templates): MARGINAL, partly present (3 shot_types +
   tailored cameras/trim already exist). Not the blocker.
2. Action hierarchy (PRIMARY/SECONDARY/TERTIARY reorder): REJECTED — proven trap.
   Slice A.3 put Action first; Run 4 action fidelity FELL 7.5->5.5. User's own
   "stop fiddling with order" conclusion.
3. Weight critical constraints: NO RELIABLE MECHANISM in SDXL text. Jian lock is
   already the most-emphasized line; Run 8 proved prompt quality != composition.
4. Scene complexity budget: ALREADY DONE (Slice A.6 env-trim + A.7 selective
   trim: establishing rich, action/interaction simplified). Image 3 stability IS
   this working.

Three of four = done or disproven. Net-new (taxonomy) is marginal.

## Infrastructure reconnaissance (this turn)
Repo search: ZERO references to controlnet / openpose / dwpose / ip-adapter /
reference-image across .py and .json. The only move that can break the
pose/interaction ceiling (pose conditioning / reference-based composition) is a
SEPARATE BUILD requiring new backend infrastructure that does NOT exist yet.
This is a build/integration decision, not a prompt edit.

## Prompt architecture is now frozen (do not edit without a new directive)
Order per prompt:
  genre, vertical 9:16 -> imperative Depict scene -> Setting -> Environment State
  -> Character Identity (incl. jian weapon lock) -> Camera (20-25% size rule)
  -> Pose -> Expression -> Lighting -> Power -> Palette -> Consistency
Selective env trim: establishing = full env; travel + climax = trimmed ambiance.

## Deferred (unchanged)
- Pose conditioning (ControlNet/OpenPose/reference): needs user authorization of a
  SEPARATE build (new backend infra absent). Highest-impact next layer per user.
- Slice B (post-generation finishing: inpaint/upscale/face-fix) + Slice C
  (automation integration) remain the originally-planned next phases.
- Weapon regression (staff vs explicit jian): persistent MODEL PRIOR. Not a prompt
  fix. Owners: xianxia-swordsman LoRA, reference conditioning, or Slice B.
- Two minor generation artifacts noted (not acted on, phase end): (a) shot-1
  foreground NPCs could be swapped for fallen statues/broken guardians via a
  negative/Setting tweak; (b) shot-2 red banner steals attention — could drop the
  banner_line from travel-shot Setting. Both are OPTIONAL prompt tweaks the user
  can request; not done this turn per "stop refining prompts" directive.
- liang.yaml duplicated-weapon Bible entry still flagged for separate hygiene
  go-ahead (Director canonicalizes at runtime; YAML untouched).
- Realistic LoRA track still pending (user asked both main-posts + realistic).

## Open decision (user to choose)
A. Accept Director as production-ready; proceed to Slice B (finishing) / Slice C
   (integration) — the originally-planned next phases.
B. Authorize a pose-conditioning BUILD (ControlNet/OpenPose/reference) — requires
   designing + standing up new backend infrastructure (verified absent). Separate
   slice, separate risk profile.
C. Freeze / stop here.
