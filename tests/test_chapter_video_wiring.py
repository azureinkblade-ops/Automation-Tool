"""CHAPTER_VIDEO_WIRING: Wan -> SVD -> MEDIA_HOLD, ComfyUI guard, >=3 s gate, app.py call sites.

CPU only. ComfyUI is never launched or contacted: the launcher runner and the Comfy transport are fakes.
ffmpeg/ffprobe are used only to make/probe tiny local mp4 files (skipped when unavailable).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import chapter_video_wiring as cvw
from tools import i2v_backend_registry as reg
from tools import media_pipeline_integration as mpi
from tools.media_validity import (
    MIN_SOCIAL_VIDEO_SECONDS,
    MediaProbeInfo,
    pass_probe_for_tests,
    validate_presented_social_video,
)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not available")


# --------------------------------------------------------------------------- config

def test_defaults_are_wan_73_frames_24fps_3s_no_loop():
    cfg = cvw.ChapterVideoConfig.from_env({})
    assert cfg.backend == "wan_22" and cfg.enabled
    assert (cfg.frames, cfg.fps) == (73, 24)
    assert cfg.min_seconds == 3.0 and cfg.loop_fallback is False
    assert cfg.problems == () and cfg.wan_clip_seconds >= 3.0
    assert cfg.backend_order == ["wan_22", "svd_xt_1_1"]


def test_one_line_switch_to_svd_and_off():
    svd = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "svd_xt_1_1"})
    assert svd.backend == "svd_xt_1_1" and svd.backend_order == ["svd_xt_1_1"] and not svd.problems
    assert cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "svd"}).backend == "svd_xt_1_1"
    off = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "off"})
    assert not off.enabled and off.backend_order == []


def test_unknown_backend_fails_closed():
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "sora"})
    assert cfg.problems and cfg.backend_order == []


@pytest.mark.parametrize("frames", ["72", "17.5", "abc", "3", "74"])
def test_frames_must_be_4n_plus_1(frames):
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": frames})
    assert cfg.problems


def test_17_frames_is_rejected_as_too_short_unless_loop_opt_in():
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": "17"})
    assert any(p.startswith("clip_shorter_than_min") for p in cfg.problems)
    looped = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": "17", "CHAPTER_VIDEO_LOOP_FALLBACK": "1"})
    assert looped.loop_fallback and not looped.problems


def test_min_seconds_is_floored_at_3():
    assert cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_MIN_SECONDS": "1"}).min_seconds == 3.0
    assert cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_MIN_SECONDS": "5"}).min_seconds == 5.0


def test_frames_fps_configurable_independently():
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": "97", "CHAPTER_VIDEO_FPS": "30"})
    assert (cfg.frames, cfg.fps) == (97, 30) and not cfg.problems
    sf = cvw.settings_factory_for(cfg)
    wan = sf("wan_22")
    assert (wan.frame_count, wan.fps) == (97, 30)
    svd = sf("svd_xt_1_1")  # SVD keeps its own native 25 frames @ 6 fps (4.2 s)
    assert (svd.frame_count, svd.fps) == (25, 6) and svd.frame_count / svd.fps >= 3.0


# --------------------------------------------------------------------------- media gate

def _probe(duration, w=1080, h=1920, frames=None):
    def fn(path):
        return MediaProbeInfo(exists=True, file_size=10**6, duration=duration, frame_count=frames or int(duration * 24),
                              width=w, height=h, decodable=True)
    return fn


def _fake_mp4(tmp_path, name="c.mp4"):
    p = tmp_path / name
    p.write_bytes(b"x" * 20000)
    return p


def test_gate_rejects_short_clip_and_accepts_3s(tmp_path):
    p = _fake_mp4(tmp_path)
    short = validate_presented_social_video(p, probe_fn=_probe(0.708), min_duration=3.0)
    assert not short.ok and short.failure_reason.startswith("MEDIA_VALIDITY_FAILED:too_short")
    ok = validate_presented_social_video(p, probe_fn=_probe(73 / 24), min_duration=3.0)
    assert ok.ok
    # library default (no floor) keeps stage-1 behaviour for existing callers
    assert validate_presented_social_video(p, probe_fn=_probe(0.708)).ok


class _FakeI2V:
    def __init__(self, raw):
        self.raw = raw

    def generate_video(self, still, *, seed, workflow_id):
        import hashlib as h
        return {"validation_status": "PASS", "video_path": str(self.raw),
                "video_sha256": h.sha256(Path(self.raw).read_bytes()).hexdigest(), "video_job_id": "j1"}


class _FakePresent:
    def __init__(self, out):
        self.out = out

    def present_video(self, raw_path, sha, src_sha, *, workflow_id):
        import hashlib as h
        return {"validation_status": "PASS", "presented_video_path": str(self.out),
                "presented_video_sha256": h.sha256(Path(self.out).read_bytes()).hexdigest(), "presentation_job_id": "p1"}


def test_pipeline_min_duration_short_clip_is_media_hold_not_still(tmp_path):
    raw = _fake_mp4(tmp_path, "raw.mp4")
    out = _fake_mp4(tmp_path, "out.mp4")
    still = tmp_path / "s.png"
    still.write_bytes(b"png")
    sha = hashlib.sha256(still.read_bytes()).hexdigest()
    short_pipe = mpi.MediaPipeline(
        store=mpi.MediaRecordStore(tmp_path / "m1"), i2v=_FakeI2V(raw), presentation=_FakePresent(out),
        media_validator=lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(0.708), **{k: v for k, v in kw.items()}),
        min_duration_seconds=3.0)
    res = short_pipe.produce_social_media(mpi.ApprovedStillRef(str(still), sha), workflow_id="w", seed=1)
    assert res.outcome == "MEDIA_HOLD" and res.asset_path is None and res.asset_kind == "none"
    assert "too_short" in res.failure_reason and res.failure_reason.startswith("VIDEO_REQUIRED_MISSING")
    good_pipe = dataclasses.replace(short_pipe, store=mpi.MediaRecordStore(tmp_path / "m2"),
                                    media_validator=lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(73 / 24), **kw))
    assert good_pipe.produce_social_media(mpi.ApprovedStillRef(str(still), sha), workflow_id="w", seed=1).outcome == "SOCIAL_READY"


# --------------------------------------------------------------------------- ComfyUI guard

class Launcher:
    """Scripted stand-in for start_comfyui_wan.bat. Records every call; never runs anything."""

    def __init__(self, status_outputs, start_rc=0):
        self.status_outputs = list(status_outputs)
        self.start_rc = start_rc
        self.calls = []

    def __call__(self, args, timeout):
        a = list(args)[1:]
        self.calls.append(a)
        if a == ["-Status"]:
            return 0, self.status_outputs.pop(0)
        if a == []:
            return self.start_rc, "START"
        if a == ["-Stop"]:
            return 0, "STOP"
        raise AssertionError(a)


BUSY_OK = "STATUS port8188_busy=True our_pid=123\nSTATUS dynvram_disabled=True"
BUSY_BAD = "STATUS port8188_busy=True our_pid=none\nSTATUS dynvram_disabled=False"
BUSY_UNREACH = "STATUS port8188_busy=True our_pid=none\nSTATUS /system_stats unreachable"
FREE = "STATUS port8188_busy=False our_pid=none\nSTATUS /system_stats unreachable"
CFG = cvw.ChapterVideoConfig.from_env({})


def test_guard_reuses_running_comfy_with_dynvram_disabled_and_never_starts_second():
    lr = Launcher([BUSY_OK])
    r = cvw.ensure_comfy_ready(CFG, lr)
    assert r.ok and not r.started_by_us and lr.calls == [["-Status"]]


@pytest.mark.parametrize("status", [BUSY_BAD, BUSY_UNREACH])
def test_guard_busy_port_without_dynvram_confirmation_is_hold_and_never_starts(status):
    lr = Launcher([status])
    r = cvw.ensure_comfy_ready(CFG, lr)
    assert not r.ok and lr.calls == [["-Status"]]  # no start, no stop


def test_guard_starts_via_launcher_only_then_confirms_status():
    lr = Launcher([FREE, BUSY_OK])
    r = cvw.ensure_comfy_ready(CFG, lr)
    assert r.ok and r.started_by_us and lr.calls == [["-Status"], [], ["-Status"]]


def test_guard_start_ok_but_dynvram_not_disabled_stops_and_holds():
    lr = Launcher([FREE, BUSY_BAD])
    r = cvw.ensure_comfy_ready(CFG, lr)
    assert not r.ok and lr.calls[-1] == ["-Stop"]


def test_guard_start_failure_rc3_never_stops_foreign_instance():
    lr = Launcher([FREE], start_rc=3)
    r = cvw.ensure_comfy_ready(CFG, lr)
    assert not r.ok and ["-Stop"] not in lr.calls


def test_guard_unparseable_status_is_hold():
    lr = Launcher(["garbage"])
    assert not cvw.ensure_comfy_ready(CFG, lr).ok and lr.calls == [["-Status"]]


# --------------------------------------------------------------------------- Wan -> SVD -> hold driver

def _still(tmp_path):
    from PIL import Image

    p = tmp_path / "still.png"
    Image.new("RGB", (768, 1344), (30, 60, 90)).save(p)
    return p


class FakePipeline:
    def __init__(self, backend, mode, tmp_path, log, duration=73 / 24):
        self.backend, self.mode, self.tmp, self.log, self.duration = backend, mode, tmp_path, log, duration

    def produce_social_media(self, still, *, workflow_id, seed):
        self.log.append((self.backend, workflow_id, seed))
        if self.mode == "hold":
            return mpi.PipelineResult(workflow_id=workflow_id, media_record_id="m", idempotency_key="k", outcome="MEDIA_HOLD",
                                      state="MEDIA_HOLD", source_image_sha256=still.source_image_sha256, asset_path=None,
                                      asset_sha256=None, asset_kind="none", raw_video_sha256=None, presented_video_sha256=None,
                                      video_creates_identity_canon=False, failure_reason=f"VIDEO_REQUIRED_MISSING:{self.backend}_failed")
        if self.mode == "raise":
            raise RuntimeError("boom")
        out = self.tmp / f"{self.backend}.mp4"
        out.write_bytes(b"v" * 20000)
        return mpi.PipelineResult(workflow_id=workflow_id, media_record_id="m", idempotency_key="k", outcome="SOCIAL_READY",
                                  state="READY", source_image_sha256=still.source_image_sha256, asset_path=str(out),
                                  asset_sha256=hashlib.sha256(out.read_bytes()).hexdigest(), asset_kind="presented_mp4",
                                  raw_video_sha256="r", presented_video_sha256="p", video_creates_identity_canon=False,
                                  failure_reason=None)


def _drive(tmp_path, modes, monkeypatch, cfg=CFG, duration=73 / 24, launcher=None, approved=True):
    log = []
    monkeypatch.setattr(cvw, "validate_presented_social_video",
                        lambda p, **kw: validate_presented_social_video(p, probe_fn=_probe(duration), **kw))
    launcher = launcher or Launcher([BUSY_OK])
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:t", store_root=tmp_path / "store", still_approved=approved, cfg=cfg,
        pipeline_builder=lambda b: FakePipeline(b, modes[b], tmp_path, log, duration), comfy_runner=launcher)
    return res, log, launcher


def test_wan_success_uses_wan_only(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch)
    assert res.ready and res.backend_used == "wan_22" and not res.fallback_used
    assert [b for b, *_ in log] == ["wan_22"]
    assert "73x24" in log[0][1]  # frames/fps are part of the job identity (no stale 17-frame reuse)


def test_wan_failure_falls_back_to_svd(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "hold", "svd_xt_1_1": "ok"}, monkeypatch)
    assert res.ready and res.backend_used == "svd_xt_1_1" and res.fallback_used
    assert [b for b, *_ in log] == ["wan_22", "svd_xt_1_1"]
    assert res.attempts[0]["backend"] == "wan_22" and res.attempts[0]["outcome"] == "MEDIA_HOLD"


def test_wan_exception_still_tries_svd(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "raise", "svd_xt_1_1": "ok"}, monkeypatch)
    assert res.ready and res.backend_used == "svd_xt_1_1"


def test_both_fail_is_media_hold_with_no_asset(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "hold", "svd_xt_1_1": "hold"}, monkeypatch)
    assert res.outcome == "MEDIA_HOLD" and not res.ready and res.asset_path is None
    assert res.hold_reason.startswith("VIDEO_REQUIRED_MISSING:") and "wan_22" in res.hold_reason and "svd_xt_1_1" in res.hold_reason


def test_svd_only_switch_never_tries_wan(tmp_path, monkeypatch):
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_BACKEND": "svd_xt_1_1"})
    res, log, _ = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, cfg=cfg)
    assert res.ready and res.backend_used == "svd_xt_1_1" and [b for b, *_ in log] == ["svd_xt_1_1"]


def test_final_media_check_rejects_short_clip_even_if_pipeline_said_ready(tmp_path, monkeypatch):
    res, log, _ = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, duration=0.708)
    assert res.outcome == "MEDIA_HOLD" and "too_short" in res.hold_reason  # both backends rejected


def test_comfy_guard_failure_holds_without_touching_pipelines(tmp_path, monkeypatch):
    res, log, lr = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, launcher=Launcher([BUSY_BAD]))
    assert res.outcome == "MEDIA_HOLD" and log == [] and "COMFY" in res.hold_reason


def test_stop_only_when_we_started_comfy(tmp_path, monkeypatch):
    _, _, lr = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, launcher=Launcher([FREE, BUSY_OK]))
    assert lr.calls[-1] == ["-Stop"]
    _, _, lr2 = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, launcher=Launcher([BUSY_OK]))
    assert ["-Stop"] not in lr2.calls


def test_off_invalid_and_unapproved_hold_before_comfy(tmp_path, monkeypatch):
    for env, approved in (({"CHAPTER_VIDEO_BACKEND": "off"}, True), ({"CHAPTER_VIDEO_FRAMES": "17"}, True), ({}, False)):
        cfg = cvw.ChapterVideoConfig.from_env(env)
        res, log, lr = _drive(tmp_path, {"wan_22": "ok", "svd_xt_1_1": "ok"}, monkeypatch, cfg=cfg, approved=approved)
        assert res.outcome == "MEDIA_HOLD" and log == [] and lr.calls == []


def test_missing_still_holds(tmp_path):
    res = cvw.produce_chapter_clip(tmp_path / "none.png", workflow_id="w", store_root=tmp_path, still_approved=True, cfg=CFG,
                                   comfy_runner=Launcher([BUSY_OK]))
    assert res.outcome == "MEDIA_HOLD" and "SOURCE_STILL_MISSING" in res.hold_reason


# --------------------------------------------------------------------------- real adapter stack with fake transport

class FakeComfy:
    """Implements I2VBackendTransport; returns a REAL mp4 of the requested frames/fps. No network, no GPU."""

    def __init__(self, tmp_path, fail=False):
        self.tmp, self.fail, self.workflows, self.uploads = tmp_path, fail, [], []

    def health_check(self):
        return True

    def free_models(self):
        return {"freed": True}

    def stage_and_upload(self, source_image, tw, th, job_id):
        self.uploads.append((tw, th))
        return "staged.png"

    def submit_and_wait(self, workflow):
        self.workflows.append(workflow)
        if self.fail:
            from tools.i2v_production_adapter import InfrastructureFailure

            raise InfrastructureFailure("comfy down")
        frames, fps = _frames_fps(workflow)
        out = self.tmp / f"gen_{len(self.workflows)}.mp4"
        subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size=720x1280:rate={fps}", "-frames:v", str(frames),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], capture_output=True, check=True)
        return {"video_bytes": out.read_bytes(), "video_path": str(out), "prompt_id": f"p{len(self.workflows)}"}


def _frames_fps(workflow):
    frames = fps = None
    for node in workflow.values():
        ins = node.get("inputs", {}) if isinstance(node, dict) else {}
        if node.get("class_type") == "EmptyHunyuanLatentVideo" or "length" in ins and "width" in ins:
            frames = ins.get("length", frames)
        if node.get("class_type") in {"CreateVideo"} or "fps" in ins:
            fps = ins.get("fps", fps)
        if "video_frames" in ins:
            frames = ins["video_frames"]
    return int(frames or 25), int(fps or 6)


@needs_ffmpeg
def test_real_stack_wan_73_frames_is_social_ready_and_3s(tmp_path):
    transport = FakeComfy(tmp_path)
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:real", store_root=tmp_path / "store", still_approved=True, cfg=CFG,
        pipeline_builder=lambda b: cvw.build_backend_pipeline(CFG, b, tmp_path / "store", transport=transport),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.ready, res.hold_reason
    assert res.backend_used == "wan_22" and (res.width, res.height) == (1080, 1920)
    assert res.duration_seconds >= 3.0 and res.frame_count == 73 and not res.looped


@needs_ffmpeg
def test_real_stack_17_frame_clip_is_held_not_posted(tmp_path):
    cfg = dataclasses.replace(CFG, frames=17, problems=())  # bypass config check: prove the media gate itself rejects 0.7 s
    transport = FakeComfy(tmp_path)
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:short", store_root=tmp_path / "store", still_approved=True,
        cfg=dataclasses.replace(cfg, backend="wan_22"),
        pipeline_builder=lambda b: cvw.build_backend_pipeline(cfg, b, tmp_path / "store", transport=transport) if b == "wan_22"
        else cvw.build_backend_pipeline(cfg, b, tmp_path / "store", transport=FakeComfy(tmp_path, fail=True)),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.outcome == "MEDIA_HOLD" and res.asset_path is None
    assert "too_short" in res.hold_reason


@needs_ffmpeg
def test_real_stack_wan_down_svd_ok_uses_stage_upload(tmp_path):
    wan_t, svd_t = FakeComfy(tmp_path, fail=True), FakeComfy(tmp_path)
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:fb", store_root=tmp_path / "store", still_approved=True, cfg=CFG,
        pipeline_builder=lambda b: cvw.build_backend_pipeline(CFG, b, tmp_path / "store", transport=wan_t if b == "wan_22" else svd_t),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.ready and res.backend_used == "svd_xt_1_1" and res.fallback_used
    assert svd_t.uploads == [(1024, 576)]  # SVD still is staged to Comfy (adapter only auto-stages Wan)
    assert res.duration_seconds >= 3.0


@needs_ffmpeg
def test_loop_fallback_is_explicit_opt_in_and_reaches_3s(tmp_path):
    cfg = cvw.ChapterVideoConfig.from_env({"CHAPTER_VIDEO_FRAMES": "17", "CHAPTER_VIDEO_LOOP_FALLBACK": "1"})
    transport = FakeComfy(tmp_path)
    res = cvw.produce_chapter_clip(
        _still(tmp_path), workflow_id="chapter-clip:loop", store_root=tmp_path / "store", still_approved=True, cfg=cfg,
        pipeline_builder=lambda b: cvw.build_backend_pipeline(cfg, b, tmp_path / "store", transport=transport,
                                                               render=cvw.LoopingRender(cfg.min_seconds)),
        comfy_runner=Launcher([BUSY_OK]))
    assert res.ready and res.duration_seconds >= 3.0


def test_verify_motion_clip_rejects_stale_and_unknown(tmp_path):
    p = _fake_mp4(tmp_path, "tiktok-video.mp4")
    assert cvw.verify_motion_clip(p, None)[0] is False
    assert cvw.verify_motion_clip(p, {"asset_sha256": "0" * 64})[1].startswith("sha256_mismatch")
    assert cvw.verify_motion_clip(tmp_path / "missing.mp4", {"asset_sha256": "a"})[1] == "video_missing"


# --------------------------------------------------------------------------- app.py call sites

@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "TIKTOK_OUTPUT_DIR", tmp_path / "tiktok-posts")
    monkeypatch.setattr(app_mod, "OUTPUT_DIR", tmp_path / "campaigns")
    monkeypatch.setenv("ENABLE_IDENTITY_PRESERVATION", "0")
    monkeypatch.delenv("CHAPTER_VIDEO_BACKEND", raising=False)
    folder = tmp_path / "tiktok-posts" / "en-5"
    folder.mkdir(parents=True)
    imgs = []
    for i in range(1, 4):
        from PIL import Image

        p = folder / f"scene-{i}.png"
        Image.new("RGB", (64, 112), (i * 40, 10, 10)).save(p)
        imgs.append(str(p))
    meta = {"abbr": "EN", "chapter": "5", "novel": "Eternal Nexus", "images": imgs, "caption": "c"}
    (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return app_mod, folder


def _ready_clip(tmp_path):
    p = tmp_path / "presented.mp4"
    p.write_bytes(b"clipbytes" * 3000)
    return p


def _fake_result(clip, ready=True, reason="VIDEO_REQUIRED_MISSING:wan_22:x|svd_xt_1_1:y"):
    if ready:
        return cvw.ChapterClipResult(outcome="SOCIAL_READY", asset_path=str(clip), asset_sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
                                     backend_used="wan_22", duration_seconds=3.04, width=1080, height=1920, frame_count=73,
                                     workflow_id="wf", source_image_path="s", source_image_sha256="x", attempts=[{"backend": "wan_22"}])
    return cvw.ChapterClipResult(outcome="MEDIA_HOLD", hold_reason=reason, attempts=[{"backend": "wan_22"}])


def test_app_ready_clip_becomes_tiktok_video_and_gate_verifies(app_env, tmp_path, monkeypatch):
    app_mod, folder = app_env
    clip = _ready_clip(tmp_path)
    seen = {}

    def fake_produce(still, **kw):
        seen["still"] = Path(still).name
        seen["wf"] = kw["workflow_id"]
        return _fake_result(clip)

    monkeypatch.setattr(cvw, "produce_chapter_clip", fake_produce)
    monkeypatch.setattr(app_mod, "media_duration_seconds", lambda p: 3.04)
    monkeypatch.setattr(cvw, "verify_motion_clip", lambda p, m, **k: (True, "ok") if (m or {}).get("asset_sha256") == hashlib.sha256(Path(p).read_bytes()).hexdigest() else (False, "sha256_mismatch"))
    build = app_mod.ensure_buffer_video(folder)
    assert build["created"] and not build["media_hold"]
    assert seen["still"] == "scene-1.png" and seen["wf"] == "chapter-clip:en-5"
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["motion_clip"]["backend"] == "wan_22" and "mediaHold" not in meta
    assert (folder / "tiktok-video.mp4").read_bytes() == clip.read_bytes()
    assert app_mod.chapter_video_wire_gate_errors(folder, meta) == []


def test_app_media_hold_has_no_video_blocks_gate_and_never_posts_images(app_env, tmp_path, monkeypatch):
    app_mod, folder = app_env
    legacy = folder / "tiktok-video.mp4"
    legacy.write_bytes(b"old slideshow" * 4000)  # a pre-existing (legacy) clip must not survive a hold
    monkeypatch.setattr(cvw, "produce_chapter_clip", lambda still, **kw: _fake_result(None, ready=False))
    build = app_mod.ensure_buffer_video(folder)
    assert build["created"] is False and build["media_hold"] is True
    assert not legacy.exists() and (folder / app_mod.CHAPTER_VIDEO_LEGACY_NAME).exists()
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["mediaHold"]["status"] == "MEDIA_HOLD" and meta["video"] == ""
    errs = app_mod.chapter_video_wire_gate_errors(folder, meta)
    assert errs and errs[0].startswith("MEDIA_HOLD")


def test_app_gate_is_strict_no_clip_or_legacy_slideshow_blocks(app_env):
    app_mod, folder = app_env
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert app_mod.chapter_video_wire_gate_errors(folder, meta)  # no video at all
    (folder / "tiktok-video.mp4").write_bytes(b"legacy" * 5000)
    assert app_mod.chapter_video_wire_gate_errors(folder, meta)  # legacy slideshow, no motion_clip provenance


def test_app_identity_hold_blocks_clip_generation(app_env, tmp_path, monkeypatch):
    app_mod, folder = app_env
    monkeypatch.setattr(app_mod, "patreon_media_identity_hold", lambda *a, **k: {"reason": "IDENTITY_APPROVAL_MISSING"})
    called = []
    monkeypatch.setattr(cvw, "produce_chapter_clip", lambda *a, **k: called.append(1))
    build = app_mod.build_reel_motion_video(folder)
    assert build["media_hold"] and "IDENTITY_HELD" in build["message"] and not called


def test_app_off_switch_restores_legacy_slideshow_builder(app_env, monkeypatch):
    app_mod, folder = app_env
    monkeypatch.setenv("CHAPTER_VIDEO_BACKEND", "off")
    calls = []
    monkeypatch.setattr(app_mod, "run_generated_video_builder", lambda *a, **k: calls.append(a) or {"created": True})
    monkeypatch.setattr(cvw, "produce_chapter_clip", lambda *a, **k: calls.append("WIRE"))
    assert app_mod.chapter_video_wire_applies(folder) is False
    app_mod.ensure_buffer_video(folder)
    assert calls and calls[0][1:] == ("make_tiktok_video.py", "tiktok-video.mp4") and "WIRE" not in calls
    assert app_mod.chapter_video_wire_gate_errors(folder, {}) == []


def test_app_deep_tiktok_is_untouched(app_env, monkeypatch):
    app_mod, folder = app_env
    deep = folder.parent / "en-7-deep"
    deep.mkdir()
    (deep / "metadata.json").write_text(json.dumps({"kind": "deep_tiktok"}), encoding="utf-8")
    assert app_mod.chapter_video_wire_applies(deep) is False


def test_app_wire_never_writes_identity_canon_flag():
    assert cvw.ChapterClipResult(outcome="MEDIA_HOLD").video_creates_identity_canon is False