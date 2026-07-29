"""pose_preprocessor.py — Slice B0 conditioning-image validation utility.

NARROW SCOPE (per user directive, 2026-07-26): this is NOT a B0 expansion.
It replaces the hand-authored skeleton with a REAL pose-detector output, following
the official Hugging Face ControlNet workflow:

    reference image (ordinary photo of a kneeling person)
            |
            v
    OpenPose detector (controlnet_aux.OpenposeDetector)
            |
            v
    detector-produced pose map (native visualization)
            |
            v
    Pose Asset Registry (points template ID -> source + derived map)
            |
            v
    SDXL OpenPose ControlNet

The Visual Director stays FROZEN. The Pose Resolver still selects a template
ID. The registry now points that ID to a SOURCE reference image and its DERIVED
detector output, instead of treating a hand-drawn map as authoritative.

Detector: controlnet_aux OpenposeDetector (prefered first, matches the documented
preprocessing path; no DWPose in this spike — adding both would be a second
variable before basic pose transfer is established).

LICENSING CAUTION (recorded, not resolved): the upstream controlnet_aux OpenPose
implementation bundles detector components with their own licenses. The exact
package version + detector model revision are recorded in the metadata sidecar.
Review before any PRODUCTION distribution. This script only produces a local
validation artifact.

Output:
  - the pose map PNG (detector native visualization) at output_path
  - a sidecar <output_path>.pose_meta.json recording:
      detector_name, detector_package_version, detector_model_revision,
      source_image (abs), source_sha256, output_dimensions, timestamp
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_openpose_condition(
    source_image: Path,
    output_path: Path,
    detector_package: str = "controlnet_aux",
    detector_name: str = "OpenposeDetector",
) -> Path:
    """Load an ordinary reference image, run the OpenPose detector, save the
    detector's native pose visualization, and write a metadata sidecar.

    Returns the pose-map path. Raises RuntimeError if the detector/import fails."""
    source_image = Path(source_image)
    output_path = Path(output_path)
    if not source_image.exists():
        raise FileNotFoundError(f"source reference image not found: {source_image}")

    try:
        from PIL import Image
        import controlnet_aux
    except Exception as exc:  # pragma: no cover - environment guard
        raise RuntimeError(f"pose preprocessor deps missing (PIL/controlnet_aux): {exc}") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(source_image).convert("RGB")
    src.thumbnail((768, 1024), Image.LANCZOS)

    det_repo = "lllyasviel/Annotators"
    det_model_revision = "main"
    # Note: controlnet_aux pins to a branch/commit internally; we record "main"
    # as the logical revision and capture the resolved commit hash from the HF
    # cache if present (best-effort, non-fatal).
    try:
        from huggingface_hub import snapshot_download
        snap = snapshot_download(det_repo, local_files_only=True)
        if "snapshots" in snap:
            det_model_revision = snap.split("snapshots/")[-1]
    except Exception:
        pass
    try:
        from controlnet_aux import OpenposeDetector
        detector = OpenposeDetector.from_pretrained(
            det_repo, hand_filename="hand_pose_model.pth", face_filename="facenet.pth",
        )
        pose_map = detector(src, hand_and_face=True)
        if hasattr(pose_map, "save"):
            pose_map.save(output_path)
        else:
            Image.fromarray(pose_map).save(output_path)
    except Exception as exc:
        raise RuntimeError(f"OpenPose detection failed: {exc}") from exc

    meta = {
        "detector_package": detector_package,
        "detector_package_version": getattr(controlnet_aux, "__version__", "unknown"),
        "detector_name": detector_name,
        "detector_model_repo": "lllyasviel/Annotators",
        "detector_model_revision": det_model_revision,
        "source_image": str(source_image.resolve()),
        "source_sha256": _sha256(source_image),
        "output_path": str(output_path.resolve()),
        "output_dimensions": list(pose_map.size) if hasattr(pose_map, "size") else None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "license_note": ("Upstream controlnet_aux OpenPose detector components carry their own "
                        "licenses; review before production distribution. Source reference image: "
                        "CC BY 2.0 (Shixart1985) - attribution required if redistributed."),
    }
    output_path.with_suffix(output_path.suffix + ".pose_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python pose_preprocessor.py <source_image> <output_pose_map>")
        raise SystemExit(2)
    out = extract_openpose_condition(Path(sys.argv[1]), Path(sys.argv[2]))
    print("POSE_MAP:", out)
    print("META:", out.with_suffix(out.suffix + ".pose_meta.json"))
