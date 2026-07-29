"""Slice B0 -- D' ControlNet guidance-END window sweep (single variable).

CONTEXT (after scale sweep, 2026-07-26):
  Varying controlnet_scale alone did NOT yield one-knee + male identity. Below
  0.65 the subject stands (kneel lost); at 0.65 it is seiza (both knees) with
  identity dipped to 3/5. So scale alone is insufficient.

NEXT SINGLE VARIABLE (second opinion's fallback): keep the scale that forces a
kneel (0.65) and vary ONLY control_guidance_end, so ControlNet sets body geometry
EARLY in denoising, then ends -> base model + LoRA regain freedom to restore male
identity + jian in later steps.
  control_guidance_end in {0.45, 0.55, 0.65, 0.75}
  control_guidance_start fixed at 0.0.

Hold: frozen Director shot-3 prompt + azink_main LoRA (0.75) + detector map B
(validation_only) + seed 917364 + scale 0.65.

Run:
  set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu/Scripts/python.exe tests/render_ab/run_dprime_window_sweep.py
Output: tests/render_ab/output/dprime_window/<end>/D.png + manifest.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
ENDS = [0.45, 0.55, 0.65, 0.75]
SEED = 917364
SHOT_INDEX = 2


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    import app as appmod
    import pose_resolver as PR
    import tests.render_ab.harness as H

    if not CONTROLNET_MODEL:
        print("ERROR: LOCAL_SD_CONTROLNET_MODEL required.")
        raise SystemExit(2)

    pose_map = PR.resolve_pose_reference({"type": "climax", "action": "kneeling, touching"})
    if not pose_map:
        print("ERROR: pose map missing")
        raise SystemExit(2)

    phrases = ["Liang enters the ruined sect hall",
                "He climbs the broken stair toward the jade altar",
                "Silver light wakes the dormant formation"]
    director_prompt = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)["director"][SHOT_INDEX]

    out_root = ROOT / "tests" / "render_ab" / "output" / "dprime_window"
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for end in ENDS:
        d = out_root / f"end_{end:0.2f}"
        d.mkdir(parents=True, exist_ok=True)
        bk = H.LocalSDAppBackend(
            app_module=appmod, orientation="vertical", quality_mode="",
            controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
            controlnet_scale=SCALE, control_guidance_start=0.0,
            control_guidance_end=end,
        )
        r = bk.render(director_prompt, d / "D.png", index=SHOT_INDEX)
        results.append({"control_guidance_end": end, "ok": r.ok, "error": r.error, "path": str(r.path)})
        print(f"end {end:0.2f}: ok={r.ok} path={r.path}")

    H.write_manifest(out_root / "manifest.dprime_window.json", {
        "experiment": "slice_b0_dprime_controlnet_window_sweep",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "single_variable": "control_guidance_end",
        "held_constant": {"prompt": "frozen Director shot 3", "lora": "azink_main (on, 0.75)",
                          "pose_map": str(pose_map), "map_status": "validation_only",
                          "seed": SEED, "controlnet_scale": SCALE,
                          "control_guidance_start": 0.0},
        "ends": ENDS,
        "results": results,
        "score_instructions": ("For each: kneel (one-knee) 1-5, male identity 1-5, "
                               "jian present 0/1-5, hand-altar 1-5. Hypothesis: ending "
                               "ControlNet earlier (0.45-0.55) keeps early kneel geometry "
                               "but lets LoRA restore male identity + jian later."),
    })
    print(f"Manifest: {out_root / 'manifest.dprime_window.json'}")


if __name__ == "__main__":
    main()
