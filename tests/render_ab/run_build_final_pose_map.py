"""Step 1 (run in .venv-gpu): generate clean synthetic kneel references.

Produces neutral full-body kneeling references (no LoRA, no ControlNet, plain
background) for later NATIVE OpenPose detection (separate step in the hermes-agent
venv, which has controlnet_aux). The detection runs in the CPU venv because
controlnet_aux is not installed in .venv-gpu.

Run:
  .venv-gpu\Scripts\python.exe tests/render_ab/run_build_final_pose_map.py
Output: assets/pose_refs/sources/clean_kneel_ref_*.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REF_PROMPTS = [
    "full body photo of a man in loose trousers, LEFT knee touching the floor, RIGHT foot flat on the "
    "ground in front of him, torso upright, both hands resting on his raised right knee, plain grey "
    "background, whole body visible, clear bent left leg with knee on ground, no occlusion",
    "side-view full body of a man proposing on one knee: left knee on the ground, right foot planted "
    "forward flat, left lower leg horizontal, hands together in front, plain beige background, "
    "unmistakable one-knee kneel, full limbs",
    "full body of a man kneeling on his left knee, right leg bent with foot on floor, leaning forward "
    "slightly, both arms down resting hands on right thigh, plain white studio background, anatomical, "
    "single person, both legs clearly differentiated",
]


def main() -> None:
    import app as appmod
    from tests.render_ab import harness as H

    refs_dir = ROOT / "assets" / "pose_refs" / "sources"
    refs_dir.mkdir(parents=True, exist_ok=True)

    prev = os.environ.get("LOCAL_SD_LORA_ENABLED")
    os.environ["LOCAL_SD_LORA_ENABLED"] = "0"
    try:
        for i, p in enumerate(REF_PROMPTS):
            d = refs_dir / f"clean_kneel_ref_v2_{i}"
            d.mkdir(parents=True, exist_ok=True)
            bk = H.LocalSDAppBackend(
                app_module=appmod, orientation="vertical", quality_mode="",
                controlnet_model="", controlnet_image=None,
            )
            r = bk.render(p, d / "ref.png", index=2)
            print(f"ref {i}: ok={r.ok} path={r.path} err={getattr(r, 'error', '')[:120]}")
    finally:
        if prev is None:
            os.environ.pop("LOCAL_SD_LORA_ENABLED", None)
        else:
            os.environ["LOCAL_SD_LORA_ENABLED"] = prev
    print("STEP1 DONE. Next: run detection in hermes-agent venv on the chosen ref.")


if __name__ == "__main__":
    main()
