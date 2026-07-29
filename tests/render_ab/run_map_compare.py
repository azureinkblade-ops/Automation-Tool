"""Map-compare driver -- corrected per-seed harness (fixes render() seed bug).

Runs the SAME frozen Director climax prompt at LoRA 0.50 + ControlNet 0.65 +
cgEnd 0.65, varying ONLY: (a) the pose map, (b) the seed.
Fresh LocalSDAppBackend per seed with seeds=(seed,) + index=0, because
LocalSDAppBackend.render() HARDCODES self.seeds[index] (harness.py:176)
and ignores any passed seed.

Usage:
  .venv-gpu\Scripts\python.exe tests\render_ab\run_map_compare.py --map B
  .venv-gpu\Scripts\python.exe tests\render_ab\run_map_compare.py --map B2a
Output: tests/render_ab/output/map_compare_<map>/<seed>/D.png + manifest.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
END = 0.65
CN_LORA_SCALE = 0.50
SEEDS = [917364, 241981, 581203, 772944]
SHOT_INDEX = 2

MAP_FILES = {
    "B": "climax_kneel_detected_B.png",
    "C": "climax_kneel_detected_C.png",
    "B2a": "climax_kneel_repaired_B2a.png",
    "B2b": "climax_kneel_repaired_B2b.png",
    "R1": "climax_kneel_detected_R1.png",
}


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    import app as appmod
    import pose_resolver as PR
    import tests.render_ab.harness as H

    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, choices=list(MAP_FILES))
    args = ap.parse_args()
    map_name = args.map
    map_path = ROOT / "assets" / "pose_refs" / MAP_FILES[map_name]
    if not map_path.exists():
        print(f"ERROR: map missing: {map_path}")
        raise SystemExit(2)
    if not CONTROLNET_MODEL:
        print("ERROR: LOCAL_SD_CONTROLNET_MODEL required.")
        raise SystemExit(2)

    phrases = ["Liang enters the ruined sect hall",
                "He climbs the broken stair toward the jade altar",
                "Silver light wakes the dormant formation"]
    director_prompt = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)["director"][SHOT_INDEX]

    out = ROOT / "tests" / "render_ab" / "output" / f"map_compare_{map_name}"
    out.mkdir(parents=True, exist_ok=True)

    prev_scale = os.environ.get("LOCAL_SD_LORA_SCALE")
    prev_enabled = os.environ.get("LOCAL_SD_LORA_ENABLED")
    os.environ["LOCAL_SD_LORA_ENABLED"] = "1"
    os.environ["LOCAL_SD_LORA_SCALE"] = str(CN_LORA_SCALE)
    results = []
    try:
        for seed in SEEDS:
            d = out / str(seed)
            d.mkdir(parents=True, exist_ok=True)
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                seeds=(seed,),
                controlnet_model=CONTROLNET_MODEL, controlnet_image=map_path,
                controlnet_scale=SCALE, control_guidance_start=0.0,
                control_guidance_end=END,
            )
            r = bk.render(director_prompt, d / "D.png", index=0)
            results.append({"seed": seed, "ok": r.ok, "error": getattr(r, "error", ""), "path": str(r.path)})
            print(f"[{map_name}] seed {seed}: ok={r.ok} err={getattr(r, 'error', '')[:120]}")
    finally:
        if prev_scale is None:
            os.environ.pop("LOCAL_SD_LORA_SCALE", None)
        else:
            os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale
        if prev_enabled is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled

    H.write_manifest(out / f"manifest.map_compare_{map_name}.json", {
        "experiment": f"map_compare_{map_name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "map": str(map_path),
        "config": {"lora_scale": CN_LORA_SCALE, "controlnet_scale": SCALE,
                   "control_guidance_end": END, "prompt": "frozen Director shot 3 (kneeling)",
                   "single_variable": "seed", "seeds": SEEDS},
        "results": results,
    })
    print(f"Manifest: {out / f'manifest.map_compare_{map_name}.json'}")


if __name__ == "__main__":
    main()
