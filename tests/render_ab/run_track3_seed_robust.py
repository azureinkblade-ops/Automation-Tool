"""Track 3 confirmation -- SAME Shot 3 prompt across RANDOM seeds at LoRA 0.50.

PURPOSE (per user activation gate 2026-07-26, item 3): prove stochastic robustness of
the kneeling configuration by rendering the SAME climax (kneeling) prompt at several
DIFFERENT random seeds. This isolates seed robustness independently of prompt variation
(the earlier 184732/582941/917364 confirm used different shot prompts per seed, which
proved prompt-generalization, not seed-stability of one prompt).

Frozen: Director shot-3 (kneeling) prompt + map C (final limb-complete) + ControlNet 0.65
+ cgEnd 0.65 + LoRA azink_main scale 0.50. Vary ONLY the seed.

Seeds: 917364 (established action seed), 241981, 581203, 772944.

Run:
  .venv-gpu\Scripts\python.exe tests/render_ab/run_track3_seed_robust.py
Output: tests/render_ab/output/track3_seed_robust/<seed>/D.png + manifest.
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
SEEDS = [917364, 241981, 581203, 772944]
SHOT_INDEX = 2  # climax kneel shot


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
        print("ERROR: pose map missing (registry should point at map C)")
        raise SystemExit(2)
    print("USING MAP:", pose_map)

    phrases = ["Liang enters the ruined sect hall",
                "He climbs the broken stair toward the jade altar",
                "Silver light wakes the dormant formation"]
    director_prompt = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)["director"][SHOT_INDEX]

    out = ROOT / "tests" / "render_ab" / "output" / "track3_seed_robust"
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
            # CRITICAL: LocalSDAppBackend.render() ignores any seed argument and
            # uses self.seeds[index] (harness.py:176). To actually vary the
            # seed, construct a FRESH backend per seed with seeds=(seed,) and
            # render at index=0 -> self.seeds[0] == seed.
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                seeds=(seed,),
                controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
                controlnet_scale=SCALE, control_guidance_start=0.0,
                control_guidance_end=END,
            )
            r = bk.render(director_prompt, d / "D.png", index=0)
            results.append({"seed": seed, "ok": r.ok, "error": getattr(r, "error", ""), "path": str(r.path)})
            print(f"seed {seed}: ok={r.ok} err={getattr(r, 'error', '')[:120]}")
    finally:
        if prev_scale is None:
            os.environ.pop("LOCAL_SD_LORA_SCALE", None)
        else:
            os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale
        if prev_enabled is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled

    H.write_manifest(out / "manifest.track3_seed_robust.json", {
        "experiment": "track3_seed_robustness_same_climax_prompt",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"lora_scale": CN_LORA_SCALE, "controlnet_scale": SCALE,
                   "control_guidance_end": END, "pose_map": str(pose_map),
                   "map_status": "production_candidate", "prompt": "frozen Director shot 3 (kneeling)",
                   "single_variable": "seed", "seeds": SEEDS},
        "results": results,
        "score_instructions": ("For each seed: one-knee kneel (5?), male identity (5?), "
                               "jian present (yes/no), Liang consistency, anatomy, environment. "
                               "Confirm kneeling config is seed-stable (no obvious regressions)."),
    })
    print(f"Manifest: {out / 'manifest.track3_seed_robust.json'}")


if __name__ == "__main__":
    main()
