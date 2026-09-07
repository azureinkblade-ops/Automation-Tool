"""CPU-only tests for pose_conditioning helpers (EA4F-2)."""
from __future__ import annotations

from pathlib import Path

import pose_conditioning as PC
import pose_resolver as PR


def test_resolve_conditioning_for_known_shot():
    shot = {"type": "climax", "action": "kneeling, touching"}
    result = PC.resolve_conditioning_for_shot(shot)
    assert result["controlnet_image"].name == "climax_kneel_detected_C.png"
    assert result["controlnet_model"]
    assert result["pose_enrichment"]["pose_condition_source"] == "detector_output"


def test_resolve_conditioning_none_for_unknown():
    result = PC.resolve_conditioning_for_shot({"type": "establishing", "action": "standing"})
    assert "controlnet_image" not in result
    assert result["pose_enrichment"]["pose_condition_source"] == "none"


def test_cli_args_empty_without_image():
    assert PC.controlnet_cli_args(controlnet_model="x") == []


def test_cli_args_complete():
    path = PR.resolve_pose_reference({"pose_template": "climax_kneel_touch_altar_v1"})
    args = PC.controlnet_cli_args(
        controlnet_model="xinsir/controlnet-openpose-sdxl-1.0",
        controlnet_image=path,
        controlnet_scale=0.85,
        control_guidance_start=0.0,
        control_guidance_end=0.75,
    )
    assert "--controlnet-model" in args
    assert "--controlnet-scale" in args
    assert args[args.index("--controlnet-scale") + 1] == "0.85"
