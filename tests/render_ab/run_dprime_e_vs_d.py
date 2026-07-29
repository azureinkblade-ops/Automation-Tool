"""Slice B0 -- E vs D isolation (clean LoRA-effect test under ControlNet).

WHY (per review 2026-07-26): B' vs D' is CONFOUNDED -- B' uses the manual Liang
kneeling prompt with LoRA OFF; D' uses the frozen Director shot-3 prompt with
LoRA ON. So B'->D' changes TWO variables (prompt AND LoRA) and CANNOT isolate
whether the LoRA causes the identity/weapon regression. This driver runs the
ONLY clean test: same frozen Director prompt + ControlNet, differing ONLY in
LoRA on/off.

Configs (everything identical except LoRA):
  E: Director prompt + ControlNet, LoRA OFF
  D: Director prompt + ControlNet, LoRA ON
Same seed, map, scale (0.65), guidance window, scheduler.

This answers: does enabling the LoRA, under identical ControlNet conditioning,
regress male identity / Liang consistency / jian? Only AFTER this can we say
"the LoRA is overwhelmed by ControlNet" vs "the combined config regresses
regardless of LoRA."

Run:
  set LOCAL_SD_CONTROLNET_MODEL=... && ^
  .venv-gpu\Scripts/python.exe tests/render_ab/run_dprime_e_vs_d.py
Output: tests/render_ab/output/dprime_e_vs_d/{E,D}/D.png + manifest.
"""

from __future__ import annotations

import os
from datetime import timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
SCALE = 0.65
END = 0.65  # use the current default window end; can be overridden by env
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
    end = float(os.environ.get("LOCAL_SD_CONTROLNET_END", str(END)))

    pose_map = PR.resolve_pose_reference({"type": "climax", "action": "kneeling, touching"})
    if not pose_map:
        print("ERROR: pose map missing")
        raise SystemExit(2)

    phrases = ["Liang enters the ruined sect hall",
                "He climbs the broken stair toward the jade altar",
                "Silver light wakes the dormant formation"]
    director_prompt = H.capture_prompts("The Hundredfold Path", "chapter text", phrases, "hp", appmod)["director"][SHOT_INDEX]

    out = ROOT / "tests" / "render_ab" / "output" / "dprime_e_vs_d"
    out.mkdir(parents=True, exist_ok=True)

    def run_cfg(label: str, lora_on: bool):
        d = out / label
        d.mkdir(parents=True, exist_ok=True)
        bk = H.LocalSDAppBackend(
            app_module=appmod, orientation="vertical", quality_mode="",
            controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map,
            controlnet_scale=SCALE, control_guidance_start=0.0,
            control_guidance_end=end,
        )
        # Force LoRA off/on regardless of ambient env.
        prev = os.environ.get("LOCAL_SD_LORA_ENABLED")
        os.environ["LOCAL_SD_LORA_ENABLED"] = "1" if lora_on else "0"
        try:
            r = bk.render(director_prompt, d / "D.png", index=SHOT_INDEX)
        finally:
            if prev is None:
                os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
            else:
                os.environ["LOCAL_SD_LORA_ENABLED"] = prev
        print(f"{label} (lora={'on' if lora_on else 'off'}): ok={r.ok} path={r.path}")
        return {"label": label, "lora_on": lora_on, "ok": r.ok, "error": r.error, "path": str(r.path)}

    e = run_cfg("E", lora_on=False)
    d = run_cfg("D", lora_on=True)

    H.write_manifest(out / "manifest.dprime_e_vs_d.json", {
        "experiment": "slice_b0_dprime_e_vs_d_lora_isolation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "single_variable": "lora_enabled (under identical Director prompt + ControlNet)",
        "held_constant": {"prompt": "frozen Director shot 3", "pose_map": str(pose_map),
                          "map_status": "validation_only", "seed": SEED,
                          "controlnet_scale": SCALE, "control_guidance_start": 0.0,
                          "control_guidance_end": end, "lora_scale_when_on": 0.75},
        "configs": {"E": e, "D": d},
        "score_instructions": ("Compare E (LoRA off) vs D (LoRA on) on: male identity, "
                               "Liang consistency (black hair, age, martial archetype), jian "
                               "present, interaction, anatomy. If D regresses vs E on identity/"
                               "jian, the LoRA is being overwhelmed by ControlNet. If both regress "
                               "equally, the issue is the combined config regardless of LoRA."),
    })
    print(f"Manifest: {out / 'manifest.dprime_e_vs_d.json'}")


if __name__ == "__main__":
    main()
