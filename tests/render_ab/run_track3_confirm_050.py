"""Track 3 confirmation -- candidate B0 config (LoRA scale 0.50) across seeds.

CONTEXT: Track 3 sweep isolated scale 0.50 as the sweet spot (one-knee kneel 5/5,
male identity 5/5, silver jian present) at frozen Director prompt + map B + ControlNet
0.65 + cgEnd 0.65. Decision-logic OUTCOME 1: promote 0.50 and confirm seed-stability
across 2-3 seeds before promotion.

Runs shot 3 (action/climax seed 917364) plus the two other per-position seeds
(establishing 184732, character 582941) at LoRA scale 0.50, identical config
otherwise. Confirms the male-id + jian + kneel combination is seed-stable.

Run:
  set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu/Scripts/python.exe tests/render_ab/run_track3_confirm_050.py
Output: tests/render_ab/output/track3_confirm_050/<seed>/D.png + manifest.
"""

from __future__ import annotations

import os
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
END = 0.65
CN_LORA_SCALE = 0.50
SEEDS = [(184732, 0), (582941, 1), (917364, 2)]  # (seed, shot_index)
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
    director_prompts = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)["director"]

    out = ROOT / "tests" / "render_ab" / "output" / "track3_confirm_050"
    out.mkdir(parents=True, exist_ok=True)

    prev_scale = os.environ.get("LOCAL_SD_LORA_SCALE")
    prev_enabled = os.environ.get("LOCAL_SD_LORA_ENABLED")
    os.environ["LOCAL_SD_LORA_ENABLED"] = "1"
    os.environ["LOCAL_SD_LORA_SCALE"] = str(CN_LORA_SCALE)
    results = []
    try:
        for seed, idx in SEEDS:
            d = out / str(seed)
            d.mkdir(parents=True, exist_ok=True)
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
                controlnet_scale=SCALE, control_guidance_start=0.0,
                control_guidance_end=END,
            )
            r = bk.render(director_prompts[idx], d / "D.png", index=idx)
            results.append({"seed": seed, "shot_index": idx, "ok": r.ok,
                             "error": getattr(r, "error", ""), "path": str(r.path)})
            print(f"seed {seed} (shot {idx}): ok={r.ok} err={getattr(r, 'error', '')[:120]}")
    finally:
        if prev_scale is None:
            os.environ.pop("LOCAL_SD_LORA_SCALE", None)
        else:
            os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale
        if prev_enabled is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled

    H.write_manifest(out / "manifest.track3_confirm_050.json", {
        "experiment": "track3_confirm_lora_050_across_seeds",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"lora_scale": CN_LORA_SCALE, "controlnet_scale": SCALE,
                   "control_guidance_end": END, "pose_map": str(pose_map),
                   "map_status": "validation_only", "prompt": "frozen Director shot 3",
                   "seeds": [s for s, _ in SEEDS]},
        "results": results,
        "score_instructions": ("For each seed: one-knee kneel (5?), male identity (5?), "
                               "jian present (yes/no), Liang consistency. Confirm the 0.50 "
                               "sweet spot is seed-stable before promoting as candidate B0."),
    })
    print(f"Manifest: {out / 'manifest.track3_confirm_050.json'}")


if __name__ == "__main__":
    main()
