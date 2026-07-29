"""Track 4 — weapon (jian) fidelity, isolated.

Authorized 2026-07-26. Pose map is FROZEN (Map B). LoRA azink_main scale
0.50, ControlNet xinsir 0.65 / cgEnd 0.65, 4 distinct seeds -- ALL frozen
from the Phase 1 baseline. The ONLY variable under test is the WEAPON
PHRASE in the Director climax prompt.

Hypothesis (single-variable, grounded): the frozen _WEAPON_LOCK says
"sheathed at his left hip" -- a sheathed blade is hidden in scabbard, which
suppresses visible-jian renders. Swapping ONLY that clause to an
"unsheathed / drawn" phrasing should raise the visible-jian rate without
touching the pose.

Method: capture the real frozen shot-3 Director prompt via
capture_prompts (so it's the ACTUAL production string), locate the
_WEAPON_LOCK substring, replace ONLY it with --weapon-phrase, render the
4 seeds with Map B. Compares jian rate vs the Map B baseline (1/4).

Single variable = weapon phrase. Pose map, LoRA, ControlNet, seeds, all
other prompt text: UNCHANGED. This is the disciplined Track 4 first step
(no open-ended search; specific hypothesis).

Usage (hermes venv import path via .venv-gpu):
  .venv-gpu\\Scripts\\python.exe tests\\render_ab\\run_track4_jian.py \
      --weapon-phrase "one standard-length Chinese jian, straight \
      double-edged blade, simple silver guard, drawn and held at his \
      left hip, blade visible"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
END = 0.65
CN_LORA_SCALE = 0.50
SEEDS = [917364, 241981, 581203, 772944]
SHOT_INDEX = 2
MAP_PATH = ROOT / "assets" / "pose_refs" / "climax_kneel_detected_B.png"


def main() -> None:
    import app as appmod
    import tests.render_ab.harness as H
    from visual_director import _WEAPON_LOCK

    ap = argparse.ArgumentParser()
    ap.add_argument("--weapon-phrase", required=True,
                    help="replacement for the frozen _WEAPON_LOCK clause ONLY")
    args = ap.parse_args()
    new_weapon = args.weapon_phrase

    if not MAP_PATH.exists():
        print(f"ERROR: Map B missing: {MAP_PATH}"); raise SystemExit(2)
    if not CONTROLNET_MODEL:
        print("ERROR: LOCAL_SD_CONTROLNET_MODEL required."); raise SystemExit(2)

    phrases = ["Liang enters the ruined sect hall",
               "He climbs the broken stair toward the jade altar",
               "Silver light wakes the dormant formation"]
    captured = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)
    director_prompts = captured["director"]
    frozen_shot3 = director_prompts[SHOT_INDEX]
    print(f"FROZEN shot-3 prompt captured ({len(frozen_shot3)} chars)")

    if _WEAPON_LOCK not in frozen_shot3:
        print(f"ERROR: _WEAPON_LOCK not found in captured prompt; abort. "
              f"Lock=\n{_WEAPON_LOCK}\n---prompt---\n{frozen_shot3}")
        raise SystemExit(2)

    # single-variable swap: ONLY the weapon clause changes
    variant_shot3 = frozen_shot3.replace(_WEAPON_LOCK, new_weapon)
    assert variant_shot3 != frozen_shot3, "weapon phrase swap produced no change"
    # safety: ensure ONLY the weapon clause differs
    n_diff = sum(1 for a, b in zip(frozen_shot3, variant_shot3) if a != b)
    print(f"Prompt char-diff vs frozen (should equal len(delta) of weapon clause): {n_diff}")

    out = ROOT / "tests" / "render_ab" / "output" / "track4_jian"
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9]+", "_", new_weapon.lower())[:40]
    run_dir = out / safe
    run_dir.mkdir(parents=True, exist_ok=True)

    prev_scale = os.environ.get("LOCAL_SD_LORA_SCALE")
    prev_enabled = os.environ.get("LOCAL_SD_LORA_ENABLED")
    os.environ["LOCAL_SD_LORA_ENABLED"] = "1"
    os.environ["LOCAL_SD_LORA_SCALE"] = str(CN_LORA_SCALE)
    results = []
    try:
        for seed in SEEDS:
            d = run_dir / str(seed)
            d.mkdir(parents=True, exist_ok=True)
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                seeds=(seed,),
                controlnet_model=CONTROLNET_MODEL, controlnet_image=MAP_PATH,
                controlnet_scale=SCALE, control_guidance_start=0.0,
                control_guidance_end=END,
            )
            r = bk.render(variant_shot3, d / "D.png", index=0)
            results.append({"seed": seed, "ok": r.ok, "error": getattr(r, "error", ""), "path": str(r.path)})
            print(f"[T4] seed {seed}: ok={r.ok} err={getattr(r, 'error', '')[:120]}")
    finally:
        if prev_scale is None:
            os.environ.pop("LOCAL_SD_LORA_SCALE", None)
        else:
            os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale
        if prev_enabled is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled

    H.write_manifest(run_dir / "manifest.track4_jian.json", {
        "experiment": "track4_jian",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "variable_under_test": "weapon phrase ONLY (frozen _WEAPON_LOCK swapped)",
        "frozen_weapon_lock": _WEAPON_LOCK,
        "variant_weapon_phrase": new_weapon,
        "prompt_char_diff_vs_frozen": n_diff,
        "map": str(MAP_PATH), "map_frozen": True,
        "config": {"lora_scale": CN_LORA_SCALE, "controlnet_scale": SCALE,
                   "control_guidance_end": END, "seeds": SEEDS,
                   "single_variable": "weapon phrase", "pose_map_unchanged": "Map B"},
        "baseline_reference": "Map B 4-seed baseline jian rate = 1/4 (581203 only)",
        "results": results,
    })
    print(f"Manifest: {run_dir / 'manifest.track4_jian.json'}")


if __name__ == "__main__":
    main()
