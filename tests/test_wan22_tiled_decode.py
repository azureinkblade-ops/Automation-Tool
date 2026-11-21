"""Wan 2.2 decode is tiled (CPU only; builds the prompt dict, never contacts ComfyUI).

The full-frame VAEDecode crashed ComfyUI with an access violation after all 20 sampling steps (Research's real
run on 25f2e71). VAEDecodeTiled with tile 512 / overlap 64 / temporal 64 / temporal_overlap 8 was clean 3 of 3
(ComfyUI-Launch\\healthcheck\\vae-tiled\\runs-20261121-155520).
"""
from __future__ import annotations

import json
from pathlib import Path

from tools import i2v_production_adapter as A

ROOT = Path(__file__).resolve().parents[1]


def _wf(**kw):
    return A.build_wan_22_ti2v_workflow(image_filename="src.png", seed=7, **kw)


def test_node_8_is_vae_decode_tiled_with_exact_inputs():
    wf = _wf()
    assert wf["8"] == {
        "class_type": "VAEDecodeTiled",
        "inputs": {
            "samples": ["3", 0],  # KSampler output, unchanged
            "vae": ["39", 0],  # VAELoader, unchanged
            "tile_size": 512,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
    }


def test_decode_still_feeds_create_video_and_no_full_frame_decode_left():
    wf = _wf(width=480, height=832, length=73)
    assert wf["57"]["inputs"]["images"] == ["8", 0]
    assert [k for k, n in wf.items() if n["class_type"] == "VAEDecode"] == []
    assert wf["8"]["inputs"]["tile_size"] == 512  # tiling does not depend on the frame size / length
    json.dumps(wf)  # still a plain JSON-able Comfy API prompt


def test_wan_ui_template_node_8_is_tiled_too():
    tpl = json.loads((ROOT / A.WAN22_WORKFLOW_TEMPLATE_RELPATH).read_text(encoding="utf-8"))
    node = next(n for n in tpl["nodes"] if n["id"] == 8)
    assert node["type"] == "VAEDecodeTiled" and node["widgets_values"] == [512, 64, 64, 8]
    assert node["properties"]["Node name for S&R"] == "VAEDecodeTiled"
    assert [i["name"] for i in node["inputs"]] == ["samples", "vae"]
    assert not [n["id"] for n in tpl["nodes"] if n.get("type") == "VAEDecode"]
