"""Track 4 T2 — LoRA-suppression isolation (evidence-only).

Authorized 2026-07-26. Frozen: Map B, original Director shot-3 prompt,
ControlNet 0.65/cgEnd 0.65, SDXL model, seeds 917364/241981/581203/772944.
ONLY variable vs Map-B baseline: azink_main LoRA 0.50 enabled -> disabled.

Gate:
- Success: visible jian >=3/4 without unacceptable pose/identity regression.
- Failure: jian <3/4 OR pose/identity regression; close T2 and move to
  inpainting (already authorized by user).

No production/registry edits. Uses the real LocalSDAppBackend path.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CONTROLNET_MODEL = os.environ.get("LOCAL_SD_CONTROLNET_MODEL", "").strip()
MAP_PATH = ROOT / "assets" / "pose_refs" / "climax_kneel_detected_B.png"
SEEDS = [917364, 241981, 581203, 772944]
SCALE = 0.65
END = 0.65
SHOT_INDEX = 2


def main() -> None:
    import app as appmod
    import tests.render_ab.harness as H

    if not CONTROLNET_MODEL:
        raise SystemExit("ERROR: LOCAL_SD_CONTROLNET_MODEL required")
    if not MAP_PATH.exists():
        raise SystemExit(f"ERROR: Map B missing: {MAP_PATH}")

    phrases = [
        "Liang enters the ruined sect hall",
        "He climbs the broken stair toward the jade altar",
        "Silver light wakes the dormant formation",
    ]
    frozen_prompt = H.capture_prompts(
        "The Hundredfold Path", "chapter text", phrases, "hp", appmod
    )["director"][SHOT_INDEX]

    out = ROOT / "tests" / "render_ab" / "output" / "track4_t2_lora_off"
    out.mkdir(parents=True, exist_ok=True)

    prev_enabled = os.environ.get("LOCAL_SD_LORA_ENABLED")
    prev_scale = os.environ.get("LOCAL_SD_LORA_SCALE")
    os.environ["LOCAL_SD_LORA_ENABLED"] = "0"
    os.environ["LOCAL_SD_LORA_SCALE"] = "0.50"  # recorded but disabled
    results = []
    try:
        for seed in SEEDS:
            seed_dir = out / str(seed)
            seed_dir.mkdir(parents=True, exist_ok=True)
            backend = H.LocalSDAppBackend(
                app_module=appmod,
                orientation="vertical",
                quality_mode="",
                seeds=(seed,),
                controlnet_model=CONTROLNET_MODEL,
                controlnet_image=MAP_PATH,
                controlnet_scale=SCALE,
                control_guidance_start=0.0,
                control_guidance_end=END,
            )
            result = backend.render(frozen_prompt, seed_dir / "D.png", index=0)
            results.append({
                "seed": seed,
                "ok": result.ok,
                "error": getattr(result, "error", ""),
                "path": str(result.path),
            })
            print(f"[T2] seed {seed}: ok={result.ok} err={getattr(result, 'error', '')[:120]}")
    finally:
        if prev_enabled is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev_enabled
        if prev_scale is None:
            os.environ.pop("LOCAL_SD_LORA_SCALE", None)
        else:
            os.environ["LOCAL_SD_LORA_SCALE"] = prev_scale

    H.write_manifest(out / "manifest.track4_t2_lora_off.json", {
        "experiment": "track4_t2_lora_off",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "azink_main LoRA suppresses jian visibility",
        "single_variable": "LOCAL_SD_LORA_ENABLED: 1 -> 0",
        "frozen": {
            "map": str(MAP_PATH),
            "prompt": "original frozen Director shot 3",
            "controlnet_scale": SCALE,
            "control_guidance_end": END,
            "seeds": SEEDS,
            "baseline_lora_scale": 0.50,
        },
        "gate": "jian >=3/4 and no unacceptable pose/identity regression",
        "results": results,
    })
    print(f"Manifest: {out / 'manifest.track4_t2_lora_off.json'}")


if __name__ == "__main__":
    main()
