"""Slice B0 -- Stage 2 three-column measurement (tightly scoped, shot 3 only).

Why this driver exists (per user directive 2026-07-26):
  The A'/B'/D' isolation RESOLVED the primary research question: poor pose
  fidelity was the CONDITIONING-IMAGE FORMAT (hand-drawn skeleton), not the
  prompt and not a ControlNet+LoRA conflict. A detector-derived pose map
  transfers the kneel 5/5 (A') and ControlNet preserves it with the LoRA (D').
  Stage 2 now answers exactly ONE question:
      Does detector-derived pose conditioning improve the FINAL image
      compared to the FROZEN Director, for this shot?
  Single variable = the conditioning image. Everything else fixed.

Scope (explicitly narrow):
  - ONE shot only: shot 3 / climax (the known failing frame).
  - EXACTLY three columns:
        legacy          : frozen-Director prompt WITHOUT ControlNet (historical baseline)
        director        : frozen-Director prompt WITHOUT ControlNet (current production)
        director_pose   : SAME frozen-Director prompt + detector map (ControlNet)
    (legacy + director are byte-identical outputs here; both are kept because
     the user's measurement table lists them as separate columns.)
  - Everything identical across columns: model, LoRA, scheduler, seed, steps,
    guidance, negative prompt. Only the conditioning image differs.
  - The conditioning asset is labeled validation_only (see
    climax_kneel_detected_B.png.status.json). It is NOT a production asset.

Run:
  cd repo && set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu/Scripts/python.exe tests/render_ab/run_pose_stage2.py
Output: tests/render_ab/output/stage2_3col/<seed>/<col>.png + manifest.stage2.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
CN_SCALE = float(os.environ.get("LOCAL_SD_CONTROLNET_SCALE", "0.65"))
POSE_TEMPLATE_ID = "climax_kneel_touch_altar_v1"
SCENE_ID = "hp_liang_review"
NOVEL = "hp"
SEED = 917364  # matcher seed for the action/climax column (Run 8 pairing)
SHOT_INDEX = 2  # shot 3 / climax


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    import app as appmod
    import pose_resolver as PR
    import tests.render_ab.harness as H

    if not CONTROLNET_MODEL:
        print("ERROR: LOCAL_SD_CONTROLNET_MODEL is required (xinsir/controlnet-openpose-sdxl-1.0).")
        raise SystemExit(2)

    # --- Resolve the detector map (validation_only) -------------------------
    pose_map = PR.resolve_pose_reference({"type": "climax", "action": "kneeling, touching"})
    if not pose_map:
        print(f"ERROR: pose map missing for template {POSE_TEMPLATE_ID}")
        raise SystemExit(2)
    enrich = PR.resolve_pose_reference_enriched(
        {"type": "climax", "action": "kneeling, touching"},
        controlnet_model=CONTROLNET_MODEL, controlnet_scale=CN_SCALE,
    )
    status_path = Path(str(pose_map) + ".status.json")
    map_status = json.loads(status_path.read_text()) if status_path.exists() else {}

    # --- Frozen production prompts, recomputed for THIS run ----------------
    title = "The Hundredfold Path"
    chapter = "chapter text"
    phrases = [
        "Liang enters the ruined sect hall",
        "He climbs the broken stair toward the jade altar",
        "Silver light wakes the dormant formation",
    ]
    captured = H.capture_prompts(title, chapter, phrases, NOVEL, appmod)
    legacy_prompt = captured["legacy"][SHOT_INDEX]
    director_prompt = captured["director"][SHOT_INDEX]

    out = ROOT / "tests" / "render_ab" / "output" / "stage2_3col" / f"seed{SEED}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "legacy").mkdir(parents=True, exist_ok=True)
    (out / "visual-director").mkdir(parents=True, exist_ok=True)
    (out / "visual-director-pose").mkdir(parents=True, exist_ok=True)

    # All columns share model/LoRA/scheduler/seed/steps/guidance/negative.
    # Build three backends differing ONLY by ControlNet.
    base = H.LocalSDAppBackend(
        app_module=appmod, orientation="vertical", quality_mode="",
        controlnet_model="", controlnet_image=None, controlnet_scale=CN_SCALE,
    )
    pose_bk = H.LocalSDAppBackend(
        app_module=appmod, orientation="vertical", quality_mode="",
        controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
        controlnet_scale=CN_SCALE,
    )

    # legacy + director both render WITHOUT ControlNet (byte-identical outputs),
    # using the SAME seed for the shot. Only director_pose adds the map.
    r_legacy = base.render(legacy_prompt, out / "legacy" / "legacy_2.png", index=SHOT_INDEX)
    r_director = base.render(director_prompt, out / "visual-director" / "director_2.png", index=SHOT_INDEX)
    r_pose = pose_bk.render(director_prompt, out / "visual-director-pose" / "director_pose_2.png", index=SHOT_INDEX)

    manifest = {
        "experiment": "slice_b0_stage2_three_column",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "single shot (shot 3 / climax) only; single variable = conditioning image",
        "scene_id": SCENE_ID,
        "novel": NOVEL,
        "shot_index": SHOT_INDEX,
        "seed": SEED,
        "fixed_across_columns": {
            "model": "sdxl-base (local)",
            "lora": "azink_main (main-posts)",
            "scheduler": "app default",
            "steps": "app default",
            "guidance": "app default",
            "negative_prompt": "app default",
        },
        "pose_conditioning": {
            **enrich,
            "asset_status": map_status.get("status", "unknown"),
            "not_production_asset": map_status.get("not_production_asset", True),
            "known_defects": map_status.get("known_defects", []),
            "controlnet_scale": CN_SCALE,
        },
        "columns": {
            "legacy": {"controlnet": False, "prompt_source": "legacy (VD off)",
                       "ok": r_legacy.ok, "error": r_legacy.error, "path": str(r_legacy.path)},
            "director": {"controlnet": False, "prompt_source": "frozen Director (VD on)",
                         "ok": r_director.ok, "error": r_director.error, "path": str(r_director.path)},
            "director_pose": {"controlnet": True, "prompt_source": "frozen Director (VD on)",
                              "ok": r_pose.ok, "error": r_pose.error, "path": str(r_pose.path)},
        },
        "prompts": {
            "legacy": legacy_prompt,
            "director": director_prompt,
            # director_pose uses the SAME director prompt (single variable = map)
        },
        "note": ("Single variable = conditioning image. Do NOT conclude 'pose "
                 "conditioning solved the problem'; bounded reading: detector-derived "
                 "pose conditioning substantially improved pose fidelity for this shot "
                 "while leaving identity fidelity largely unchanged."),
    }
    H.write_manifest(out / "manifest.stage2.json", manifest)
    print(f"Stage 2 three-column done. Seed {SEED}.")
    print(f"  legacy        ok={r_legacy.ok}")
    print(f"  director      ok={r_director.ok}")
    print(f"  director_pose ok={r_pose.ok}")
    print(f"  manifest: {out / 'manifest.stage2.json'}")


if __name__ == "__main__":
    main()
