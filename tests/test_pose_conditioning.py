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


def test_remember_shots_and_index():
    PC.clear_shots()
    shots = [
        {"type": "establishing", "action": "standing at entrance"},
        {"type": "travel", "action": "climbing stairs"},
        {"type": "climax", "action": "kneeling, touching altar"},
    ]
    PC.remember_shots(shots, meta={"novel": "hp"})
    assert PC.shot_for_index(2)["type"] == "climax"
    cond = PC.resolve_conditioning_for_index(2)
    assert cond.get("controlnet_image") is not None
    # flag off -> empty kwargs
    import os
    os.environ.pop("POSE_CONTROLNET_ENABLED", None)
    assert PC.kwargs_for_generator(index=2, prompt="kneeling") == {}
    os.environ["POSE_CONTROLNET_ENABLED"] = "1"
    kw = PC.kwargs_for_generator(index=2, prompt="")
    assert "controlnet_image" in kw
    os.environ.pop("POSE_CONTROLNET_ENABLED", None)
    PC.clear_shots()


def test_resolve_from_text_kneel():
    r = PC.resolve_conditioning_from_text("Liang kneeling on one knee touching the altar")
    assert r.get("controlnet_image") is not None
