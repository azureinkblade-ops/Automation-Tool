# Handoff: Rendered A/B evidence gate - RUN 1 (main-posts LoRA, HP/Liang)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commits this run: e0dcdba (seed fix), a875b46 (app.py NameError fix), f3ddf34, 1e57437.

## What ran
- Engine: local Stable Diffusion (app main source), same local_image_generator.py
  + SDXL (models/sdxl-base) + azink_main LoRA (0.75) the posts/videos use.
- Scene: HP / Liang, 3 phrases (establishing / character / action).
- Control: SAME seed per paired legacy[i]/director[i] = 184732 / 582941 / 917364.
- 6 images rendered in the SD GPU runtime (.venv-gpu). No generation failures.
- You executed: .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd
- A real bug surfaced and was fixed first: app.py referenced
  ALLOW_EXTERNAL_IMAGE_FALLBACK in a startup log line BEFORE it was defined
  (line 124) -> NameError swallowed by a bare except -> "dependency check skipped".
  Moved the definition above the log. Import now clean; SD status ready=True.

## Control verification (manifest control_check)
ALL paired fields matched across legacy[i] vs director[i]:
  SDXL checkpoint, refiner (none), LoRA path+weight (0.75), scheduler (dpm),
  steps, guidance, size (768x1344), negative prompt, and SEED.
Generator effectiveSeed == requestedSeed for all 6 images (no seedMismatch).
=> The ONLY variable between each pair is the prompt. Control held.

## Scores (1-5), vision-evaluated on the 6 real renders
| criterion            | legacy | director |
|----------------------|--------|---------|
| character_identity   | 1      | 4       |
| canon_accuracy       | 1      | 3       |
| shot_differentiation | 4      | 5       |
| sequence_coherence   | 2      | 4       |
| mobile_readability   | 4      | 5       |
| artifact_control     | 4      | 4       |
| overall_improvement  | 1      | 4       |
Liang recognizable: legacy 0/3, director 3/3 (but only 2/3 male-Liang-consistent;
shot 2 flipped to a female cultivator).

## Gate (harness.evaluate_gate, not eyeball)
recommend_continue = TRUE. All four checks PASS:
  overall_improvement Director 4 > Legacy 1
  canon_accuracy Director 3 >= Legacy 1 (no regression)
  Liang identity >=2/3 Director images: 3/3
  three-shot differentiation >=4: Director 5

## Honest caveats (Director is NOT an unqualified win)
1. Legacy prompts produced near-EMPTY architectural shots (tiny/absent Liang).
   Director clearly wins on character presence + canon detail. BUT this partly
   reflects that the legacy prompt is a generic "cinematic cover art" string with
   no character anchor, while the Director prompt names hair/robes/weapon. The A/B
   is faithful (single variable = prompt) and still shows the Director yields a
   usable character where legacy yields a location.
2. Director canon drift observed:
   - shot 1: robes rendered RED, not jade/green (canon says jade sect robes).
   - shot 2: gender flipped to FEMALE (Liang is male) - consistency break within
     the Director set; weapon shown as jian vs staff across shots.
   - The 'silver edged weapon, silver edged' DUPLICATE token I flagged earlier is
     still present in director prompts (liang.yaml malformed weapon entry coerced
     to a string + canonical weapon). Should be deduped.
3. The liang.yaml Bible defect (line 28 unquoted parens; weapon list mixes a
   'NO weapon at Ch140' exception) is the ROOT cause of some canon noise. The
   Director handled it gracefully (canon_warnings fired, filtered the exception)
   but the data should be corrected at source.
4. This run used the MAIN-POSTS LoRA only. You asked to test BOTH realistic and
   main-posts. Realistic is a separate run (same seeds, --lora-track realistic).

## Artifacts (local, not committed - large binaries)
tests/render_ab/output/{legacy,director}/*.png  (6 images)
tests/render_ab/output/manifest.json            (control + traces)
tests/render_ab/output/manifest.scored.json     (scores + gate)
tests/render_ab/output/report.scored.md          (side-by-side scoring sheet)

## Next steps (do NOT start Slice 2 yet)
- Run the REALISTIC LoRA variant (hold seeds 184732/582941/917364) for the
  same 6-prompt A/B, so the new workflow is evaluated on both tracks.
- Then decide: if both tracks show Director >= legacy on usable sequence, the
  gate supports advancing to Slice 2 (reference image library / IP-Adapter etc.).
- Recommended Director fixes before any activation: dedup the weapon token;
  correct liang.yaml weapon entry + remove the chapter-exception leak.
