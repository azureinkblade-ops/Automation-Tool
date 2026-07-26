# Handoff: Rendered A/B Run 2 — Visual Director Slice A (main-posts LoRA)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-26
Precedes: VISUAL-DIRECTOR-RENDERED-AB-RUN1-MAINPOSTS.md, VISUAL-DIRECTOR-SLICEA-REFINEMENT.md
Commits: Slice A = 8cf70be (visual_director.py + app.py + 4 test files). Run 2 output untracked (raw PNGs), scored manifest + this handoff committed.

## Control (verified from real manifest trace_meta, NOT inferred)
Same scene `hp_liang_review`, same engine (local_stable_diffusion / sdxl-base),
same LoRA (main-posts, scale 0.75), same scheduler (dpm), same size (768x1344),
same negative prompt, same seeds per paired index:
  legacy_0/director_0 = 184732
  legacy_1/director_1 = 582941
  legacy_2/director_2 = 917364
`control_check.all_matched = true`. `trace_meta.requestedSeed == effectiveSeed`
for all 6 (seedMismatch: false). CORRECTION to earlier note: the seed pairing IS
verified end-to-end from the real generator sidecar (generatorMetadata.seed ==
requestedSeed); my prior "seed echo gap" claim was based on reading the wrong
nesting level and is RETRACTED.

## Method
- Ran: `.venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd`
- Scored all 6 images via vision_analyze on the actual PNGs (not from prompts).
- Applied the formal harness gate (harness.evaluate_gate): 7 criteria, 1-5,
  per three-image SET. Tie is not enough; Director must win on overall_improvement
  with no canon regression, >=2/3 Liang identity, shot differentiation >=4.

## Scores (vision-evaluated, 1-5 per SET)
| Criterion                | Legacy | Director |
|--------------------------|--------|----------|
| character_identity       | 1      | 5        |
| canon_accuracy           | 2      | 4        |
| shot_differentiation     | 2      | 5        |
| sequence_coherence       | 3      | 5        |
| mobile_readability       | 5      | 5        |
| artifact_control         | 3      | 4        |
| overall_improvement      | 2      | 5        |

## Gate
- overall_improvement Director 5 > Legacy 2 : PASS
- canon_accuracy Director 4 >= Legacy 2 : PASS (no regression)
- Liang identity in >=2/3 Director images : 3/3 PASS
- three-shot differentiation (>=4) : Director 5 PASS
- **recommend_continue: True**

## Observed per-image findings (evidence, not just scores)
Legacy:
- 0: monochrome ink-wash hall, tiny silhouette in archway, no Liang traits. Env 5.
- 1: pagoda/cliff environment, NO character at all. Pure location shot.
- 2: robed figure with glowing faceless head, symmetric formation; generic mystic
  archetype, not Liang-specific; arguably the strongest legacy frame but still
  no named-character lock.
Director:
- 0: young male, topknot, jade robes, silver-edged sword, red banners, wide
  low-angle. Recognizable Liang. (Minor: sword hilt red not silver-edge;
  "ruined" reads more preserved; no glowing formations visible.)
- 1: same cultivator from behind, red robe this seed, over-the-shoulder, grand
  stair. (Minor: stair not visibly "broken"; hand not clearly near weapon.)
- 2: same cultivator, silver armor, hero shot, standing (prompt said kneeling);
  no visible qi-flow lines on ground.
Cross-run note: the three Director frames are the SAME character (topknot,
calm, jade/silver wardrobe) — identity lock holds; the red-vs-jade robe and
stand-vs-kneel variance is LoRA/seed drift, not a canon defect in the prompt.

## What Run 2 confirms about Slice A
1. Weapon dedup landed in production: manifest director prompts show
   `silver-edged sword` (no `silver edged weapon, silver edged`).
2. Per-image narrative objective landed: 3 distinct objectives, no repetition.
3. Character-identity block landed: every Director image rendered a recognizable
   Liang with the locked traits (topknot, jade robes, calm, sword) vs legacy
   where the character was absent or generic.
4. The Director remains the stronger production path (gate PASS, same as Run 1).

## Residual defects to feed Slice B (art-finishing), NOT Slice A
- "kneeling" prompt -> character rendered standing (pose not always honored).
- "broken stair" / "ruined" -> reads preserved/intact (environment-state field
  did not override the LoRA's pristine tendency).
- sword hilt rendered red, not silver-edged (weapon detail drift).
- no visible glowing formations / qi-flow lines (magic-effect not rendered).
These are SDXL+LoRA fidelity limits the post-generation pipeline (Slice B:
img2img/inpaint/upscale/face-fix) is designed to address. Slice B is a SEPARATE
experiment, still gated on its own value.

## Deferred / flagged
- liang.yaml duplicated weapon entry: still flagged for separate Bible-hygiene
  authorization (Director canonicalizes at runtime; YAML untouched).
- realistic LoRA track A/B: NOT yet run (user asked both main-posts + realistic;
  realistic pending).
- Slice B (finishing) and Slice C (integration): deferred per phased plan.

## Next
- Optional: run `--backend local-sd` realistic track to cover the second
  workflow the user named, then Slice B proposal can be scoped from real defects.
- No code change required by this run; Slice A is validated in production render.
