"""Slice B0 A-D isolation driver (reuses the WORKING Stage 1 subprocess launch).

Goal: isolate WHICH variable causes the Stage 1 identity regression, per the
user's requested pipeline-validation (not another prompt experiment).

We reuse H.LocalSDAppBackend's exact render() (the same subprocess invocation
that succeeded in Stage 1) but make two knobs variable that the production
backend hard-codes:
  - lora_enabled (Test A/B = off, C/D = on)
  - the prompt string (A = "standing person", B/C/D = Liang kneel)
  - controlnet on/off (A/B/C = off, D = on)

Tests:
  A: base SDXL, NO LoRA, minimal prompt "standing person", pose image
     Q: does the POSE actually transfer (kneel) with no LoRA to interfere?
  B: base SDXL, NO LoRA, Liang kneel prompt, pose image
     Q: does kneeling happen when the prompt asks for it + pose image?
  C: base SDXL, LoRA, NO ControlNet   -> identity check (should be Liang)
  D: base SDXL, LoRA, ControlNet        -> exactly where does identity die?

Same seed (917364), model, dimensions, steps, guidance across all four.

Run from repo root in the SD runtime:
  .venv-gpu\\Scripts\\python.exe tests/render_ab/run_pose_iso.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import pose_resolver as PR  # noqa: E402
import tests.render_ab.harness as H  # noqa: E402


class IsoBackend(H.LocalSDAppBackend):
    """LocalSDAppBackend variant with lora + custom prompt knobs for isolation."""

    def __init__(self, *a, lora_enabled: bool = True, **kw):
        super().__init__(*a, **kw)
        self._lora_enabled = lora_enabled

    def render(self, prompt: str, out_path: Path, index: int = 0) -> "H.RenderResult":
        # Force LoRA off for tests A/B by overriding the env the backend reads.
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
    pose_img = PR.resolve_pose_reference({"type": "climax", "action": "kneeling one knee touching altar"})

    out = ROOT / "tests" / "render_ab" / "output" / "iso"
    out.mkdir(parents=True, exist_ok=True)

    minimal = "standing person"
    liang = ("male xianxia cultivator Liang kneeling on one knee before a jade altar, "
             "left hand on the cold stone, jade sect robes, silver jian sword at left hip")

    # A: no lora, minimal prompt, controlnet on
    bA = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=False,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_img, controlnet_scale=0.65)
    rA = bA.render(minimal, out / "A.png", index=2)
    # B: no lora, liang prompt, controlnet on
    bB = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=False,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_img, controlnet_scale=0.65)
    rB = bB.render(liang, out / "B.png", index=2)
    # C: lora ON, controlnet OFF
    bC = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=True)
    rC = bC.render(liang, out / "C.png", index=2)
    # D: lora ON, controlnet ON
    bD = IsoBackend(app_module=appmod, orientation="vertical", quality_mode="", lora_enabled=True,
                    controlnet_model=CONTROLNET_MODEL, controlnet_image=pose_img, controlnet_scale=0.65)
    rD = bD.render(liang, out / "D.png", index=2)

    print(f"A (no-lora/minimal/pose): ok={rA.ok} -> {rA.path}")
    print(f"B (no-lora/liang/pose):   ok={rB.ok} -> {rB.path}")
    print(f"C (lora/no-pose):          ok={rC.ok} -> {rC.path}")
    print(f"D (lora/pose):             ok={rD.ok} -> {rD.path}")
    print("Outputs in:", out)
    print("Inspect A/B for POSE transfer (kneel?) and C vs D for IDENTITY (where Liang dies).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
