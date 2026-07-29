"""Evidence replay for the feature-flagged Stage 2 refinement service.

Produces a quarantined pending-review candidate. It never replaces the source.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app as appmod
import tests.render_ab.harness as H
from local_object_refinement_backend import LocalSDXLInpaintBackend
from object_refinement import ObjectRefinementService, RefinementRequest


def main() -> int:
    source = ROOT / "tests/render_ab/output/map_compare_B/917364/D.png"
    mask = ROOT / "tests/render_ab/output/track4_inpaint/seed917364_jian_mask.png"
    guide = ROOT / "tests/render_ab/output/track4_inpaint/seed917364_jian_guide.png"
    work = ROOT / "tests/render_ab/output/stage2_refinement_replay"
    for required in (source, mask, guide):
        if not required.exists():
            raise SystemExit(f"missing replay prerequisite: {required}")

    phrases = [
        "Liang enters the ruined sect hall",
        "He climbs the broken stair toward the jade altar",
        "Silver light wakes the dormant formation",
    ]
    frozen = H.capture_prompts(
        "The Hundredfold Path", "chapter text", phrases, "hp", appmod
    )["director"][2]
    prompt = (
        frozen
        + ". LOCAL REFINEMENT ONLY: preserve the supplied rigid jian geometry. "
          "One unmistakable standard-length Chinese jian in a dark teal scabbard, "
          "wrapped hilt, simple horizontal silver guard, hanging naturally at "
          "Liang's outer left hip. Preserve robe, hands, pose, face, and scene."
    )
    os.environ["VISUAL_OBJECT_REFINEMENT_ENABLED"] = "1"
    backend = LocalSDXLInpaintBackend(
        python_executable=str(ROOT / ".venv-gpu/Scripts/python.exe"),
        script_path=ROOT / "local_object_refiner.py",
        model_path=ROOT / "models/sdxl-base",
        lora_path=ROOT / "loras/main-posts/pytorch_lora_weights.safetensors",
        seed=917364,
        strength=0.25,
        steps=35,
        guidance_scale=7.0,
        negative_prompt=(
            "duplicate sword, multiple weapons, floating weapon, ribbon, sash, rope, "
            "tassel, fabric strip, malformed hand, extra fingers, text, watermark"
        ),
    )
    result = ObjectRefinementService(backend=backend).refine(
        source,
        RefinementRequest(
            object_type="jian",
            target_region="outer left hip",
            prompt=prompt,
            mask_path=mask,
            guide_path=guide,
        ),
        work,
    )
    print({
        "status": result.status,
        "effective_output": str(result.output_path),
        "candidate": str(result.candidate_path),
        "provenance": str(result.provenance_path),
        "diff": str(result.diff_path),
    })
    if result.status != "pending_review" or result.output_path != source:
        raise SystemExit("replay violated pending-review quarantine contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
