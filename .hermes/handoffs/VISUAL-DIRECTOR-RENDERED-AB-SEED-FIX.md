# Handoff: Rendered A/B seed-control fix (paired seeds)

Author: Hermes (editing session 20260715_060146_c55923)
Date: 2026-07-25
Commit: (run `git rev-parse --short HEAD`)
Parent: f3ddf34 (A/B via local SD), 1e57437 (doc)

## User-supplied experimental-control correction (applied)
The previous LocalSDAppBackend chose a fresh random seed per render
(seed = self.seed or random.randint(...)), which would confound the A/B:
a different seed alone can radically change SDXL composition/quality, so
legacy[i] vs director[i] would not isolate the Visual Director.

FIX (harness.py + run_real_ab.py):
- LocalSDAppBackend.seeds = (184732, 582941, 917364) per shot position:
  establishing, character, action.
- render(prompt, out_path, index=i): uses seeds[index] for BOTH legacy[i] and
  director[i]. The ONLY variable between a pair is the prompt.
- Trace records requestedSeed AND effectiveSeed (read back from the generator's
  .local-sd.json metadata). seedMismatch flag raised if they differ -> exposed
  as a failure in the manifest (control broken).
- run_ab returns seed_assignment so the manifest shows the pairing explicitly.
- Driver --seeds arg (default 184732,582941,917364) for explicit control.
- Driver adds control_check: for each pair, compares model/refiner/LoRA path/
  weight/scheduler/steps/guidance/size/negative/seed between legacy[i] and
  director[i]; surfaces all_matched so the run is accepted only after the
  control is confirmed identical.
- Failure exposure also flags SEED MISMATCH and SEED NOT PAIRED.

## Confirmed scene + run protocol (user)
- Novel The Hundredfold Path, character Liang. Phrases:
  1 Liang enters the ruined sect hall
  2 He climbs the broken stair toward the jade altar
  3 Silver light wakes the dormant formation
- The integration only replaces the returned list[str] prompts, so the faithful
  test is: positive prompt -> enhance_local_sd_prompt() -> same SDXL + LoRA +
  same negative + same seed -> image. package["negative_prompt"] is NOT injected
  (production does not consume it); both paths use the env negative prompt.
- Run only after the seed fix. Accept the run only after the manifest shows
  identical paired values for: seed, SDXL checkpoint, refiner, LoRA path+weight,
  scheduler, steps, guidance, width/height, enhanced-prompt treatment, negative.

## GPU runtime (how to run)
The local SD pipeline runs under the dedicated GPU interpreter:
.venv-gpu\Scripts\python.exe (created by "Install Local Image GPU - venv-gpu.bat";
LOCAL_SD_PYTHON env or auto-detect via local_sd_python()). The harness imports
app under that interpreter so local_sd_python() resolves to .venv-gpu.

Run command (from the repo root, in the GPU runtime):
  .venv-gpu\Scripts\python.exe tests\render_ab\run_real_ab.py --backend local-sd

This is NOT run by Hermes (codex sandbox lacks diffusers/torch). The user runs
it in the SD GPU runtime. No API billing (local GPU).

## This commit
tests/render_ab/harness.py (seed pairing + control trace), run_real_ab.py
(--seeds + control_check + seed failure exposure), test_harness.py (10/10 pass,
fake_run echoes requested seed so the control check is exercised). No generation
fired. No Director/AIVSB/Bible/metadata changes. Slice 2 not started. AIVSB frozen.
