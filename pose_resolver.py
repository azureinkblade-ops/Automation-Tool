"""Pose Resolver + Pose Asset Registry for the Visual Director (Slice B0).

RESPONSIBILITY SPLIT (per user directive, Run 8 follow-up, refined 2026-07-26):
  Visual Director  -> semantic pose intent (free text), e.g.
                       "kneeling on left knee, torso leaning forward,
                        left hand touching altar"
  Pose Resolver    -> deterministic pose-template ID, e.g.
                       climax_kneel_touch_altar_v1
  Pose Asset Reg.  -> (a) SOURCE reference image (ordinary photo of the pose)
                       (b) DERIVED detector pose-map (controlnet_aux OpenPose output)
                       The template points to BOTH; the detector map is the
                       conditioning input fed to ControlNet. The hand-drawn map
                       is no longer authoritative (it failed A/B isolation).
  SDXL ControlNet  -> consumes the detector pose-map.

The Director chooses the TEMPLATE; it does not draw the skeleton. This keeps
image-generation mechanics out of the Director and preserves its prompt freeze.

This module is PURE (no torch/diffusers import) so it can be unit-tested on the
CPU test runtime and imported by the Director without GPU dependencies.

Evidence boundary: every resolved pose carries provenance (source image, its
sha256, the detector name, and the derived map's sha256) so a future run can
never silently switch between hand-authored and detector-generated maps. See
resolve_pose_reference_enriched().
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Optional

# Pose-template registry.
# Each template maps to a SOURCE reference image (ordinary photo of the pose)
# and a DERIVED detector pose-map (the actual ControlNet conditioning input).
# The spike wires exactly ONE template (the known failing frame: shot 3).
# Additional templates are added here as the pose library grows.
POSE_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "pose_refs"

POSE_TEMPLATES: Dict[str, Dict[str, str]] = {
    # Shot 3: Liang kneeling on one knee, left hand touching altar, formation
    # activating. Source = real CC BY 2.0 photo of a man kneeling
    # (Shixart1985); map = controlnet_aux OpenPose detector output.
    "climax_kneel_touch_altar_v1": {
        # Map C = FINAL limb-complete one-knee kneel (production_candidate).
        # Replaces map B (validation_only, right-arm + merged-hip defects).
        # Map C is an AUTHORED pose spec (COCO keypoints) rendered via a
        # self-contained skeleton renderer -- native detection of kneeling
        # photos mis-places hips/ankles and fails to encode a grounded kneel.
        # Validated by random-seed re-render at LoRA 0.50 (see Track 3 confirm).
        "source": "sources/kneeling_man_altar_user_ref_2026-07-26.png",
        "map": "climax_kneel_detected_C.png",
    },
}


def _sha256(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def pose_template_id_for(shot: dict) -> Optional[str]:
    """Resolve a deterministic pose-template ID from a Visual Director shot dict.

    The Director sets ``shot["pose_template"]`` (it owns the *selection*, not the
    drawing). If absent, fall back to a keyword heuristic so the resolver still
    works for shots that only carry a free-text ``action``. Returns None when no
    template matches (caller then renders without ControlNet).
    """
    # 1. Explicit selection by the Director (preferred, deterministic).
    explicit = (shot.get("pose_template") or "").strip()
    if explicit in POSE_TEMPLATES:
        return explicit
    # 2. Heuristic for the spike's known failing frame: a climax/ritual shot
    #    whose action mentions kneeling + touching.
    action = (shot.get("action") or "").lower()
    shot_type = (shot.get("type") or "").lower()
    if ("kneel" in action or "kneeling" in action) and "touch" in action:
        return "climax_kneel_touch_altar_v1"
    if shot_type in {"climax", "ritual"} and "kneel" in action:
        return "climax_kneel_touch_altar_v1"
    return None


def pose_reference_path(template_id: str) -> Optional[Path]:
    """Return the absolute path to the DERIVED detector pose-map PNG, or None if
    the template is unknown or the map file is missing.

    NOTE: the authoritative conditioning input is the *detector map*, not a
    hand-authored skeleton. If the map is missing (detector not yet run), this
    returns None and the caller proceeds without ControlNet.
    """
    if template_id not in POSE_TEMPLATES:
        return None
    path = POSE_ASSET_DIR / POSE_TEMPLATES[template_id]["map"]
    return path if path.exists() else None


def pose_source_path(template_id: str) -> Optional[Path]:
    """Return the absolute path to the SOURCE reference image, or None."""
    if template_id not in POSE_TEMPLATES:
        return None
    path = POSE_ASSET_DIR / POSE_TEMPLATES[template_id]["source"]
    return path if path.exists() else None


def resolve_pose_reference(shot: dict) -> Optional[Path]:
    """Full resolution: shot -> template ID -> derived detector map path.

    Returns None when no usable pose map exists (caller then proceeds without
    ControlNet). This is the path fed to ControlNet.
    """
    template_id = pose_template_id_for(shot)
    if not template_id:
        return None
    return pose_reference_path(template_id)


def resolve_pose_reference_enriched(shot: dict, *,
                                   detector_package: str = "controlnet_aux",
                                   detector_name: str = "OpenposeDetector",
                                   controlnet_model: str = "",
                                   controlnet_scale: float = 0.65) -> Dict[str, object]:
    """Return full provenance for the manifest evidence boundary.

    Distinguishes pose_condition_source = "detector_output" and records the
    source image + its sha256, the detector name, and the derived map's sha256,
    plus the controlnet model/scale. A future run can never silently switch
    between hand-authored and detector-generated maps because the source + hashes
    are explicit.
    """
    template_id = pose_template_id_for(shot)
    if not template_id:
        return {"pose_condition_source": "none"}
    src = pose_source_path(template_id)
    mp = pose_reference_path(template_id)
    return {
        "pose_condition_source": "detector_output" if mp else "none",
        "pose_template_id": template_id,
        "pose_detector": f"{detector_package}:{detector_name}" if mp else None,
        "pose_source_image": str(src.resolve()) if src else None,
        "pose_source_sha256": _sha256(src) if src else None,
        "pose_map_sha256": _sha256(mp) if mp else None,
        "controlnet_model": controlnet_model or None,
        "controlnet_scale": controlnet_scale,
    }
