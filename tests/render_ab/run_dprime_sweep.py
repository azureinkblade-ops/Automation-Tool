"""Slice B0 -- D' ControlNet-strength sweep (single variable).

WHY (per second-opinion review, 2026-07-26, accepted):
  Stage 2 proved pose transfer works (A'/B'/D' all kneel), but the COMBINED
  Director + LoRA + ControlNet config (scale 0.65, window 0.0-0.75) FAILED the
  non-regression gate: identity regressed male->androgynous (4->2) and the jian
  vanished. B' (no LoRA) keeps male 4/5 + jian 4/5, so the LoRA identity/weapon
  signal is being overwhelmed by ControlNet at the current strength.

EXPERIMENT (single variable = controlnet_scale):
  Hold: frozen Director shot-3 prompt + azink_main LoRA + detector map (B,
        validation_only) + seed 917364 + default steps/guidance/scheduler.
  Vary ONLY controlnet_scale across {0.30, 0.40, 0.50, 0.65}.
  Objective: find the LOWEST scale that still forces the kneel, so the LoRA/
  Director identity + weapon survive.

NOT a three-column comparison. This is the next isolated experiment before any
Stage 2 promotion decision.

Run:
  set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu/Scripts/python.exe tests/render_ab/run_dprime_sweep.py
Output: tests/render_ab/output/dprime_sweep/<scale>/D.png + manifest.dprime_sweep.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALES = [0.30, 0.40, 0.50, 0.65]
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

    title, chapter = "The Hundredfold Path", "chapter text"
    phrases = [
        "Liang enters the ruined sect hall",
        "He climbs the broken stair toward the jade altar",
        "Silver light wakes the dormant formation",
    ]
    captured = H.capture_prompts(title, chapter, phrases, "hp", appmod)
    director_prompt = captured["director"][SHOT_INDEX]

    out_root = ROOT / "tests" / "render_ab" / "output" / "dprime_sweep"
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for scale in SCALES:
        scale_dir = out_root / f"scale_{scale:0.2f}"
        scale_dir.mkdir(parents=True, exist_ok=True)
        bk = H.LocalSDAppBackend(
            app_module=appmod, orientation="vertical", quality_mode="",
            controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
            controlnet_scale=scale,
        )
        r = bk.render(director_prompt, scale_dir / "D.png", index=SHOT_INDEX)
        results.append({
            "controlnet_scale": scale,
            "ok": r.ok, "error": r.error, "path": str(r.path),
        })
        print(f"scale {scale:0.2f}: ok={r.ok} path={r.path}")

    manifest = {
        "experiment": "slice_b0_dprime_controlnet_strength_sweep",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "single_variable": "controlnet_scale",
        "held_constant": {
            "prompt": "frozen Director shot 3", "lora": "azink_main (on, 0.75)",
            "pose_map": str(pose_map), "map_status": "validation_only",
            "seed": SEED, "steps": "app default", "guidance": "app default",
            "control_guidance_start": 0.0, "control_guidance_end": 0.75,
        },
        "scales": SCALES,
        "results": results,
        "score_instructions": (
            "For each scale image score 1-5: kneel retained, male identity "
            "retained, black hair retained, jian present, anatomy, interaction "
            "direction. Find the LOWEST scale that still forces the kneel while "
            "preserving male identity + jian."),
    }
    H.write_manifest(out_root / "manifest.dprime_sweep.json", manifest)
    print(f"Manifest: {out_root / 'manifest.dprime_sweep.json'}")


if __name__ == "__main__":
    main()
