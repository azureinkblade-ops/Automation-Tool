"""Pose conditioning helpers for ControlNet wiring.

Pure CPU module. Builds generator CLI args from a Visual Director shot +
pose_resolver registry. Keeps ControlNet mechanics out of visual_director and
out of ad-hoc app.py string assembly.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pose_resolver as PR


DEFAULT_CONTROLNET_MODEL = "xinsir/controlnet-openpose-sdxl-1.0"


def controlnet_defaults() -> Dict[str, Any]:
    return {
        "controlnet_model": os.environ.get("LOCAL_SD_CONTROLNET_MODEL", DEFAULT_CONTROLNET_MODEL).strip()
        or DEFAULT_CONTROLNET_MODEL,
        "controlnet_scale": float(os.environ.get("LOCAL_SD_CONTROLNET_SCALE", "0.65")),
        "control_guidance_start": float(os.environ.get("LOCAL_SD_CONTROL_GUIDANCE_START", "0.0")),
        "control_guidance_end": float(os.environ.get("LOCAL_SD_CONTROL_GUIDANCE_END", "0.75")),
    }


def resolve_conditioning_for_shot(shot: dict) -> Dict[str, Any]:
    """Return kwargs suitable for create_local_stable_diffusion_image(**kwargs).

    If no pose map is available, returns empty dict (caller proceeds without ControlNet).
    """
    defaults = controlnet_defaults()
    pose_path = PR.resolve_pose_reference(shot)
    enrich = PR.resolve_pose_reference_enriched(
        shot,
        controlnet_model=defaults["controlnet_model"],
        controlnet_scale=defaults["controlnet_scale"],
    )
    if not pose_path:
        return {"pose_enrichment": enrich}
    return {
        "controlnet_model": defaults["controlnet_model"],
        "controlnet_image": pose_path,
        "controlnet_scale": defaults["controlnet_scale"],
        "control_guidance_start": defaults["control_guidance_start"],
        "control_guidance_end": defaults["control_guidance_end"],
        "pose_enrichment": enrich,
    }


def controlnet_cli_args(
    *,
    controlnet_model: str = "",
    controlnet_image: Optional[Path] = None,
    controlnet_scale: float | None = None,
    control_guidance_start: float | None = None,
    control_guidance_end: float | None = None,
) -> List[str]:
    """Build local_image_generator ControlNet CLI fragments. Empty when incomplete."""
    model = (controlnet_model or "").strip()
    image = Path(controlnet_image) if controlnet_image else None
    if not model or image is None or not image.exists():
        return []
    defaults = controlnet_defaults()
    scale = defaults["controlnet_scale"] if controlnet_scale is None else controlnet_scale
    start = defaults["control_guidance_start"] if control_guidance_start is None else control_guidance_start
    end = defaults["control_guidance_end"] if control_guidance_end is None else control_guidance_end
    return [
        "--controlnet-model", model,
        "--controlnet-image", str(image),
        "--controlnet-scale", str(scale),
        "--control-guidance-start", str(start),
        "--control-guidance-end", str(end),
    ]
