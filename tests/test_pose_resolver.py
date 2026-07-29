"""GPU-free tests for the Slice B0 pose-conditioning scaffold.

Covers:
  - pose_resolver: template ID resolution + asset registry path (no torch).
  - generator command construction includes ControlNet args only when a model
    + image are supplied (verified via create_local_stable_diffusion_image's
    command list, mocked).
  - harness LocalSDAppBackend forwards ControlNet args only when set (no GPU).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pose_resolver as PR  # noqa: E402


def test_resolver_known_template_id():
    shot = {"type": "climax", "action": "kneeling on one knee, left hand touching altar, silver qi"}
    tid = PR.pose_template_id_for(shot)
    assert tid == "climax_kneel_touch_altar_v1"
    # Conditioning input is the DERIVED detector map (not a hand-authored skeleton).
    path = PR.resolve_pose_reference(shot)
    assert path is not None and path.exists()
    assert path.name == "climax_kneel_detected_B.png"
    # Source reference is tracked separately.
    src = PR.pose_source_path(tid)
    assert src is not None and src.exists()


def test_resolver_explicit_template_wins():
    shot = {"pose_template": "climax_kneel_touch_altar_v1"}
    assert PR.pose_template_id_for(shot) == "climax_kneel_touch_altar_v1"


def test_resolver_unknown_action_returns_none():
    shot = {"type": "establishing", "action": "standing at the entrance looking up"}
    assert PR.pose_template_id_for(shot) is None
    assert PR.resolve_pose_reference(shot) is None


def test_resolver_unknown_template_no_path():
    assert PR.pose_reference_path("nonexistent_template") is None


def test_resolver_enriched_provenance():
    shot = {"type": "climax", "action": "kneeling, touching"}
    enrich = PR.resolve_pose_reference_enriched(
        shot, controlnet_model="xinsir/controlnet-openpose-sdxl-1.0", controlnet_scale=0.65)
    assert enrich["pose_condition_source"] == "detector_output"
    assert enrich["pose_template_id"] == "climax_kneel_touch_altar_v1"
    assert enrich["pose_detector"].startswith("controlnet_aux:")
    assert enrich["pose_source_image"].endswith("kneeling_man_altar_user_ref_2026-07-26.png")
    assert enrich["pose_source_sha256"] is not None
    assert enrich["pose_map_sha256"] is not None
    assert enrich["controlnet_model"] == "xinsir/controlnet-openpose-sdxl-1.0"
    assert enrich["controlnet_scale"] == 0.65


def test_resolver_enriched_none():
    enrich = PR.resolve_pose_reference_enriched({"type": "x", "action": "y"})
    assert enrich["pose_condition_source"] == "none"


def test_app_command_includes_controlnet_when_set(monkeypatch):
    """create_local_stable_diffusion_image must add ControlNet args only when
    model + image are present; otherwise the command is unchanged."""
    import app as appmod
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        # Simulate a successful generator: create a minimal valid PNG at --output
        # so create_local_stable_diffusion_image's post-run checks pass.
        try:
            out_idx = command.index("--output")
            outp = Path(command[out_idx + 1])
            outp.parent.mkdir(parents=True, exist_ok=True)
            png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                   b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
                   b"\xc0\xf0\x1f\x00\x05\x05\x02\x00\x9d\xc5\xd8\x1f\x00\x00\x00\x00IEND\xaeB`\x82")
            outp.write_bytes(png)
            # Pad to >=1024 bytes so create_local_stable_diffusion_image's
            # size gate (>=1024) passes for the fake render.
            if outp.stat().st_size < 2048:
                outp.write_bytes(png + b"\x00" * 2048)
            # Also write the generator metadata sidecar the function expects.
            meta = outp.with_suffix(outp.suffix + ".local-sd.json")
            meta.write_text("{\"seed\": %s}" % command[command.index("--seed") + 1], encoding="utf-8")
        except Exception:
            pass
        class _R:
            returncode = 0
            stderr = ""
            stdout = ""
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(appmod, "local_sd_python", lambda: "python")
    monkeypatch.setattr(appmod, "LOCAL_IMAGE_GENERATOR_SCRIPT", ROOT / "local_image_generator.py")
    # Force SD status ready with a dummy model so the function builds a command.
    monkeypatch.setattr(appmod, "local_stable_diffusion_status", lambda: {
        "ready": True, "model": "stabilityai/stable-diffusion-xl-base-1.0",
        "refinerModel": "", "scheduler": "dpm", "qualityMode": "premium",
        "timeoutSeconds": 360, "dependencies": {}, "script": str(appmod.LOCAL_IMAGE_GENERATOR_SCRIPT),
    })
    monkeypatch.setattr(appmod, "lora_track_for_prompt", lambda *a, **k: "main")
    monkeypatch.setattr(appmod, "find_lora_weights_for_track", lambda *a, **k: None)
    monkeypatch.setattr(appmod, "enhance_local_sd_prompt", lambda p, **k: p)
    monkeypatch.setattr(appmod, "mark_image_used", lambda *a, **k: {})
    monkeypatch.setattr(appmod, "save_promo_rotation_state", lambda *a, **k: None)

    out = ROOT / "tests" / "render_ab" / "output" / "_cmd_test.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    # No ControlNet -> args absent.
    appmod.create_local_stable_diffusion_image("p", out, seed=1)
    assert "--controlnet-model" not in captured["command"]

    # With ControlNet -> args present.
    pose_img = PR.resolve_pose_reference({"type": "climax", "action": "kneeling, touching"})
    appmod.create_local_stable_diffusion_image(
        "p", out, seed=1,
        controlnet_model="xinsir/controlnet-openpose-sdxl-1.0",
        controlnet_image=pose_img, controlnet_scale=0.85,
        control_guidance_start=0.0, control_guidance_end=0.75,
    )
    cmd = captured["command"]
    assert "--controlnet-model" in cmd
    assert "xinsir/controlnet-openpose-sdxl-1.0" in cmd
    assert "--controlnet-image" in cmd
    assert "--controlnet-scale" in cmd
    # scale value passed
    i = cmd.index("--controlnet-scale")
    assert cmd[i + 1] == "0.85"
    assert "--control-guidance-start" in cmd
    assert "--control-guidance-end" in cmd


def test_harness_backend_forwards_controlnet(monkeypatch):
    import tests.render_ab.harness as H
    captured = {}

    class _FakeR:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return _FakeR()

    monkeypatch.setattr(subprocess, "run", fake_run)
    app = type("A", (), {})()
    app.local_stable_diffusion_status = lambda: {
        "ready": True, "model": "m", "refinerModel": "", "scheduler": "dpm",
        "qualityMode": "premium", "timeoutSeconds": 360, "dependencies": {}, "script": "x.py",
    }
    app.lora_track_for_prompt = lambda *a, **k: "main"
    app.find_lora_weights_for_track = lambda *a, **k: None
    app.enhance_local_sd_prompt = lambda p, **k: p
    app.local_sd_python = lambda: "python"
    app.LOCAL_IMAGE_GENERATOR_SCRIPT = ROOT / "local_image_generator.py"
    app.ROOT = ROOT
    app._LOCAL_SD_GPU_LOCK = type("L", (), {"__enter__": lambda s: None, "__exit__": lambda s, *a: None})()
    app.write_image_provider_trace = lambda *a, **k: None

    pose_img = PR.resolve_pose_reference({"type": "climax", "action": "kneeling, touching"})
    bk = H.LocalSDAppBackend(app_module=app, controlnet_model="xinsir/controlnet-openpose-sdxl-1.0",
                             controlnet_image=pose_img, controlnet_scale=0.45)
    bk.render("p", ROOT / "tests" / "render_ab" / "output" / "_hb_test.png", index=2)
    assert "--controlnet-model" in captured["command"]
    assert "0.45" in captured["command"]
