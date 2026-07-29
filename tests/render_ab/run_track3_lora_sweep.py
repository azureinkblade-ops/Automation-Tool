"""Track 3 -- narrow LoRA-compatibility slice (separate from B0).

SCOPE (per user 2026-07-26): keep FROZEN and unchanged: Director prompt, detector
map B (validation_only), ControlNet settings (scale 0.65, cgEnd 0.65), seed 917364,
base model, scheduler, steps, guidance. Vary ONLY the LoRA contribution:
  azink_main scale: 0.00, 0.20, 0.35, 0.50, 0.65, 0.75
Reuse existing E vs D renders for 0.00 and 0.75 (sidecar-confirmed matching frozen
config); render only the intermediate scales 0.20/0.35/0.50/0.65.

TARGET: lowest NONZERO LoRA scale that materially improves intended visual style
without losing male identity or the kneeling pose.

Run:
  set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu/Scripts/python.exe tests/render_ab/run_track3_lora_sweep.py
Output: tests/render_ab/output/track3_lora_sweep/<scale>/D.png + manifest.
  Reused E/D images are symlinked/copied into the same output dir for side-by-side
  scoring with their original paths recorded in the manifest.
"""

from __future__ import annotations

import os
import shutil
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
END = 0.65
SEED = 917364
SHOT_INDEX = 2
ED_ROOT = ROOT / "tests" / "render_ab" / "output" / "dprime_e_vs_d"
# scales to actually render (0.00 and 0.75 are reused from E vs D)
RENDER_SCALES = [0.20, 0.35, 0.50, 0.65]
REUSE = {0.00: ("E", "LoRA OFF"), 0.75: ("D", "LoRA ON 0.75")}


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

    out = ROOT / "tests" / "render_ab" / "output" / "track3_lora_sweep"
    out.mkdir(parents=True, exist_ok=True)

    results = []

    # Reuse E (0.00) and D (0.75) if their sidecar matches the frozen config.
    for sc, (label, desc) in REUSE.items():
        src = ED_ROOT / label / "D.png"
        dst = out / f"lora_{sc:0.2f}.png"
        if src.exists():
            shutil.copyfile(src, dst)
            results.append({"lora_scale": sc, "reused_from": str(src),
                            "desc": desc, "path": str(dst)})
            print(f"scale {sc:0.2f}: REUSED {label} -> {dst}")
        else:
            print(f"scale {sc:0.2f}: E/D source missing, will render")
            RENDER_SCALES.append(sc)

    # Render the intermediate scales. LoRA scale is read by the backend from the
    # LOCAL_SD_LORA_SCALE / LOCAL_SD_LORA_ENABLED env vars (not a constructor arg).
    for sc in RENDER_SCALES:
        if any(r["lora_scale"] == sc for r in results):
            continue
        d = out / f"render_{sc:0.2f}"
        d.mkdir(parents=True, exist_ok=True)
        prev_scale = os.environ.get("LOCAL_SD_LORA_SCALE")
        prev_enabled = os.environ.get("LOCAL_SD_LORA_ENABLED")
        os.environ["LOCAL_SD_LORA_ENABLED"] = "1"
        os.environ["LOCAL_SD_LORA_SCALE"] = str(sc)
        try:
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
                controlnet_scale=SCALE, control_guidance_start=0.0,
                control_guidance_end=END,
            )
            r = bk.render(director_prompt, d / "D.png", index=SHOT_INDEX)
        except Exception as ex:
            r = type("R", (), {"ok": False, "error": f"EXC {type(ex).__name__}: {ex}",
                               "path": str(d / "D.png")})()
        finally:
            if prev_scale is None:
                os.environ.pop("LOCAL_SD_LORA_SCALE", None)
            else:
                os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale
            if prev_enabled is None:
                os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
            else:
                os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled
        results.append({"lora_scale": sc, "ok": r.ok, "error": getattr(r, "error", ""), "path": str(r.path)})
        print(f"scale {sc:0.2f}: ok={r.ok} err={getattr(r, 'error', '')[:200]} path={r.path}")

    H.write_manifest(out / "manifest.track3_lora_sweep.json", {
        "experiment": "track3_lora_compatibility_sweep",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "single_variable": "azink_main lora_scale",
        "frozen": {"prompt": "frozen Director shot 3", "pose_map": str(pose_map),
                   "map_status": "validation_only", "controlnet_scale": SCALE,
                   "control_guidance_end": END, "seed": SEED, "base_model": "sdxl-base",
                   "scheduler": "frozen", "steps": "frozen", "guidance": "frozen"},
        "scales": [0.00, 0.20, 0.35, 0.50, 0.65, 0.75],
        "results": results,
        "score_instructions": ("For each: one-knee pose (survives?), male identity "
                               "(locate collapse threshold), Liang consistency (hair/age/"
                               "martial), jian presence (does any scale help?), anatomy, "
                               "environment, interaction (hand toward altar). Target: lowest "
                               "nonzero scale improving style without losing male id or kneel."),
        "decision_logic": ("1) intermediate works -> promote + rerun 2-3 seeds. "
                           "2) every nonzero feminizes -> LoRA unsuitable, park + retrain. "
                           "3) male survives but jian absent -> split weapon into own slice."),
    })
    print(f"Manifest: {out / 'manifest.track3_lora_sweep.json'}")


if __name__ == "__main__":
    main()
