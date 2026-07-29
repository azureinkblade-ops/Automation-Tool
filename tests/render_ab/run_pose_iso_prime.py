"""Slice B0 A'-B'-D' validation driver (detector-produced pose map).

NARROW validation (per user directive 2026-07-26): re-run the A/B/D
isolation using the REAL detector-produced pose map (controlnet_aux OpenPose
output of a kneeling reference photo) instead of the hand-authored skeleton.
This tests the leading hypothesis: the Stage 1 failure was the conditioning
IMAGE format, not a ControlNet+LoRA incompatibility.

Reuses the WORKING Stage 1 subprocess launch (torch loads only via the app
harness; a bare CLI call to local_image_generator.py fails to import torch).

Tests (seed 917364, 30 steps, guidance 7.0, identical base model):
  A': base SDXL, NO LoRA, minimal "kneeling person" prompt, DETECTOR map
      Pass: unmistakable kneeling posture; basic arm direction follows ref.
      If A' fails -> stop. Implicates checkpoint/preprocessing/pipeline, not LoRA.
  B': base SDXL, NO LoRA, full Liang-kneel prompt, DETECTOR map
      Pass: kneeling retained; altar interaction at least directionally correct.
  D': base SDXL, LoRA ON, full frozen Director prompt, DETECTOR map
      Pass: male Liang-like identity; kneeling retained; no severe anatomical
      regression; costume broadly canonical.
  (C does not need rerunning: the unconditioned LoRA path was already
   validated in the prior isolation.)

Output: tests/render_ab/output/iso_prime/{A,B,D}.png + a manifest with
the evidence-boundary provenance (pose_condition_source=detector_output,
pose_detector, pose_source_image, pose_source_sha256, pose_map_sha256,
controlnet_model, controlnet_scale).

Run from repo root in the SD runtime:
  .venv-gpu\\Scripts\\python.exe tests/render_ab/run_pose_iso_prime.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import pose_resolver as PR  # noqa: E402
import tests.render_ab.harness as H  # noqa: E402


class IsoBackend(H.LocalSDAppBackend):
    def __init__(self, *a, lora_enabled: bool = True, **kw):
        super().__init__(*a, **kw)
        self._lora_enabled = lora_enabled

    def render(self, prompt: str, out_path: Path, index: int = 0):
        prev = os.environ.get("LOCAL_SD_LORA_ENABLED")
        if not self._lora_enabled:
            os.environ["LOCAL_SD_LORA_ENABLED"] = "0"
        try:
            return super().render(prompt, out_path, index=index)
        finally:
            if prev is None:
                os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
            else:
                os.environ["LOCAL_SD_LORA_ENABLED"] = prev


def main() -> int:
    st = appmod.local_stable_diffusion_status()
    if not st.get("ready"):
        missing = [n for n, r in (st.get("dependencies") or {}).items() if not r]
        print(f"ERROR: local SD not ready (missing: {', '.join(missing) or 'generator'}).")
        return 2

    CONTROLNET_MODEL = os.environ.get(
        "LOCAL_SD_CONTROLNET_MODEL",
        "C:/Users/David/Documents/Automation tool/models/controlnet-openpose-sdxl-1.0",
    ).strip()
    CN_SCALE = float(os.environ.get("LOCAL_SD_CONTROLNET_SCALE", "0.65"))

    # Resolve the DETECTOR-produced map via the registry (source + derived map).
    shot_meta = {"type": "climax", "action": "kneeling on one knee, left hand touching altar"}
    pose_map = PR.resolve_pose_reference(shot_meta)
    if pose_map is None:
        print("ERROR: detector pose map not found. Run pose_preprocessor.py first.")
        return 2
    enrich = PR.resolve_pose_reference_enriched(
        shot_meta, controlnet_model=CONTROLNET_MODEL, controlnet_scale=CN_SCALE)
    print("Detector map:", pose_map)
    print("Provenance:", json.dumps(enrich, indent=2))

    SEED = int(os.environ.get("ISO_PRIME_SEED", "917364"))
    out = ROOT / "tests" / "render_ab" / "output" / "iso_prime" / f"seed{SEED}"
    out.mkdir(parents=True, exist_ok=True)
    minimal = "a person kneeling on one knee, hands together in prayer"
    liang = ("male xianxia cultivator Liang kneeling on one knee before a jade altar, "
             "left hand on the cold stone, silver qi flowing through the dormant formation, "
             "jade sect robes, silver jian sword at left hip")

    SEED_MAP = {184732: 0, 582941: 1, 917364: 2}
    IDX = SEED_MAP.get(SEED, 2)
    # A': no lora, minimal prompt, detector map
    bA = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=False,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map, controlnet_scale=CN_SCALE)
    rA = bA.render(minimal, out / "A.png", index=IDX)
    # B': no lora, full liang prompt, detector map
    bB = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=False,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map, controlnet_scale=CN_SCALE)
    rB = bB.render(liang, out / "B.png", index=IDX)
    # D': lora ON, full frozen Director prompt, detector map
    # (use the real Director prompt for shot 3 so D' mirrors production intent)
    prompts = H.capture_prompts(
        "The Hundredfold Path", "chapter text",
        ["Liang enters the ruined sect hall",
         "He climbs the broken stair toward the jade altar",
         "Silver light wakes the dormant formation"], "hp", appmod)
    director_prompt = prompts["director"][2]
    bD = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=True,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_map, controlnet_scale=CN_SCALE)
    rD = bD.render(director_prompt, out / "D.png", index=IDX)

    manifest = {
        "experiment": "slice_b0_iso_prime_detector_map",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "control": "single variable vs prior run = conditioning image (detector map vs hand-drawn); model/LoRA/scale identical",
        "pose_provenance": enrich,
        "results": {
            "A_prime": {"ok": rA.ok, "path": rA.path, "error": rA.error},
            "B_prime": {"ok": rB.ok, "path": rB.path, "error": rB.error},
            "D_prime": {"ok": rD.ok, "path": rD.path, "error": rD.error,
                        "director_prompt": director_prompt},
        },
    }
    (out / "manifest.iso_prime.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"A' (no-lora/minimal/detector-map): ok={rA.ok}")
    print(f"B' (no-lora/liang/detector-map):  ok={rB.ok}")
    print(f"D' (lora/director/detector-map):    ok={rD.ok}")
    print("Outputs in:", out)
    print("Inspect: A' must show unmistakable kneeling; B' keeps it; D' keeps it + Liang identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
