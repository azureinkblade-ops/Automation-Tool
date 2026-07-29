"""Slice B0 Stage 1 viability spike driver (run on the local SD GPU runtime).

Renders ONLY shot 3 (Liang kneeling on one knee, left hand touching altar,
formation activating) under two conditions, identical in every respect except
the ControlNet conditioning:

  A. Frozen Director  (no ControlNet)
  B. Frozen Director  + xinsir OpenPose ControlNet (pose reference)

Same seed, model, LoRA, dimensions, steps, guidance, prompt. The ONLY variable
is the ControlNet conditioning image + scale.

Per the user's Stage 1 gate, the conditioned image must:
  - actually depict kneeling (pose compliance)
  - not fail / not require unacceptable VRAM offloading
  - keep Liang-like identity
  - not be anatomically worse than the unconditioned render

And the result must succeed on >= 2 seeds (one seed can flatter/punish).

Run (from repo root, in the .venv-gpu SD runtime):
  .venv-gpu\\Scripts\\python.exe tests/render_ab/run_pose_stage1.py
Set env LOCAL_SD_CONTROLNET_MODEL=xinsir/controlnet-openpose-sdxl-1.0 first
(the default). Output lands in tests/render_ab/output/stage1/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import pose_resolver as PR  # noqa: E402
import tests.render_ab.harness as H  # noqa: E402

SCENE = (
    "The Hundredfold Path", "chapter text",
    ["Liang enters the ruined sect hall",
     "He climbs the broken stair toward the jade altar",
     "Silver light wakes the dormant formation"],
    "hp",
)
POSE_INDEX = 2  # shot 3 (climax)
SEEDS = (184732, 582941, 917364)  # test on all three paired seeds
CONTROLNET_SCALE = float(os.environ.get("LOCAL_SD_CONTROLNET_SCALE", "0.65"))
CONTROL_GUIDANCE_START = float(os.environ.get("LOCAL_SD_CONTROL_GUIDANCE_START", "0.0"))
CONTROL_GUIDANCE_END = float(os.environ.get("LOCAL_SD_CONTROL_GUIDANCE_END", "0.75"))
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "xinsir/controlnet-openpose-sdxl-1.0").strip()


def main() -> int:
    if not CONTROLNET_MODEL:
        print("ERROR: set LOCAL_SD_CONTROLNET_MODEL (e.g. xinsir/controlnet-openpose-sdxl-1.0).")
        return 2
    st = appmod.local_stable_diffusion_status()
    if not st.get("ready"):
        missing = [n for n, r in (st.get("dependencies") or {}).items() if not r]
        print(f"ERROR: local SD not ready (missing: {', '.join(missing) or 'generator'}).")
        return 2

    prompts = H.capture_prompts(*SCENE, appmod)
    director_prompts = prompts["director"]
    shot_prompt = director_prompts[POSE_INDEX]
    print(f"Shot {POSE_INDEX} Director prompt:\n  {shot_prompt}\n")

    pose_img = PR.resolve_pose_reference({"type": "climax", "action": shot_prompt})
    if pose_img is None:
        print("ERROR: pose-reference asset not resolved.")
        return 2
    print(f"Pose reference: {pose_img}\n")

    out_root = ROOT / "tests" / "render_ab" / "output" / "stage1"
    out_root.mkdir(parents=True, exist_ok=True)

    base_bk = H.LocalSDAppBackend(app_module=appmod, orientation="vertical", quality_mode="")
    pose_bk = H.LocalSDAppBackend(
        app_module=appmod, orientation="vertical", quality_mode="",
        controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_img,
        controlnet_scale=CONTROLNET_SCALE,
        control_guidance_start=CONTROL_GUIDANCE_START,
        control_guidance_end=CONTROL_GUIDANCE_END,
    )

    results = []
    for seed in SEEDS:
        # Render shot 3 WITHOUT ControlNet (use index=POSE_INDEX so same seed maps).
        r_no = base_bk.render(shot_prompt, out_root / f"no_pose_seed{seed}.png", index=POSE_INDEX)
        # Render shot 3 WITH ControlNet (same seed).
        r_yes = pose_bk.render(shot_prompt, out_root / f"pose_seed{seed}.png", index=POSE_INDEX)
        results.append({
            "seed": seed,
            "no_pose": {"ok": r_no.ok, "path": r_no.path, "error": r_no.error,
                        "trace": r_no.trace_meta},
            "pose": {"ok": r_yes.ok, "path": r_yes.path, "error": r_yes.error,
                     "trace": r_yes.trace_meta},
        })
        print(f"seed {seed}: no_pose ok={r_no.ok} | pose ok={r_yes.ok}"
              + (f" ERR={r_yes.error[:120]}" if not r_yes.ok else ""))

    # Persistence check: must succeed on >= 2 seeds.
    pose_ok_count = sum(1 for r in results if r["pose"]["ok"])
    print(f"\nPose renders succeeded on {pose_ok_count}/{len(SEEDS)} seeds.")
    print("Outputs in:", out_root)
    print("Next: visually inspect each pose_*.png for kneeling compliance + "
          "identity/no-anatomy-regression vs no_pose_*.png.")
    return 0 if pose_ok_count >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
