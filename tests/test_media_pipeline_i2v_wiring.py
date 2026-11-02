"""CPU-only tests for tools.media_pipeline_i2v_wiring (fakes; no GPU/network/ComfyUI)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pytest

from tools import i2v_presentation_adapter as pa
from tools import i2v_production_adapter as i2v
from tools.media_pipeline_i2v_wiring import (
    PresentationAdapterPort,
    ProductionI2VPort,
    build_default_media_pipeline,
    clip_ref_from_i2v_result,
    default_settings_for_backend,
)
from tools.media_pipeline_integration import ApprovedStillRef, MediaPipeline, PipelineOutcome
from tools.media_validity import pass_probe_for_tests, validate_presented_social_video


def _pass_validator(path, **kwargs):
    kw = dict(kwargs)
    kw["min_bytes"] = 1
    return validate_presented_social_video(path, probe_fn=pass_probe_for_tests(), **kw)


@dataclass
class FakeGenResult:
    validation_status: str
    video_path: Optional[str]
    video_sha256: Optional[str]
    video_job_id: str
    backend_id: str
    i2v_width: int
    i2v_height: int
    frame_count: int
    fps: int
    video_creates_identity_canon: bool = False
    video_path_durable: bool = True


class FakeI2VAdapter:
    """Mimics ImageToVideoAdapter.generate_video; writes a durable raw clip under store_root."""

    def __init__(self, store_root: Path, status: str = "PASS"):
        self.store_root = Path(store_root)
        self.status = status
        self.calls: List[dict] = []

    def generate_video(self, source_image, motion_plan=None, backend_id=i2v.BACKEND_ID_SVD_XT_1_1,
                       seed=0, settings=None, *, workflow_id=None, **_kw):
        assert isinstance(source_image, i2v.SourceImageRef)
        self.calls.append({"backend_id": backend_id, "settings": settings, "seed": seed,
                           "workflow_id": workflow_id, "source": source_image})
        data = f"raw|{backend_id}|{seed}|{source_image.source_image_sha256}".encode()
        d = self.store_root / "i2v_jobs" / "videos"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{backend_id}_{seed}.mp4"
        p.write_bytes(data)
        return FakeGenResult(
            validation_status=self.status, video_path=str(p),
            video_sha256=hashlib.sha256(data).hexdigest(), video_job_id=f"job-{backend_id}",
            backend_id=backend_id, i2v_width=settings.target_width, i2v_height=settings.target_height,
            frame_count=settings.frame_count, fps=settings.fps,
        )


class SpyPresentationAdapter:
    def __init__(self, inner):
        self.inner = inner
        self.clips: List[Any] = []

    def present_video(self, clip, **kw):
        self.clips.append(clip)
        return self.inner.present_video(clip, **kw)


def _still(tmp_path: Path) -> ApprovedStillRef:
    p = tmp_path / "still.png"
    p.write_bytes(b"approved-still-bytes")
    return ApprovedStillRef(image_path=str(p), source_image_sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def _build(tmp_path: Path, env: dict, render=pa.mock_render):
    root = tmp_path / "store"
    fake = FakeI2VAdapter(root)
    pres = SpyPresentationAdapter(pa.I2VPresentationAdapter(
        store=pa.PresentationJobStore(root / "presentation_jobs"), render=render, output_dir=root / "presented"))
    pipe = build_default_media_pipeline(root, i2v_adapter=fake, presentation_adapter=pres,
                                        environ=env, media_validator=_pass_validator)
    return pipe, fake, pres, root


def test_default_wiring_builds_without_gpu_or_network(tmp_path):
    pipe = build_default_media_pipeline(tmp_path / "s", environ={})
    assert isinstance(pipe, MediaPipeline)
    assert isinstance(pipe.i2v, ProductionI2VPort)
    assert isinstance(pipe.i2v.adapter, i2v.ImageToVideoAdapter)
    assert isinstance(pipe.presentation, PresentationAdapterPort)
    assert isinstance(pipe.presentation.adapter, pa.I2VPresentationAdapter)
    assert pipe.presentation.adapter.render is pa.default_ffmpeg_render
    assert pipe.presentation.i2v_port is pipe.i2v
    for sub in ("i2v_jobs", "presentation_jobs", "media_records"):
        assert (tmp_path / "s" / sub).is_dir()


def test_svd_is_default_when_env_unset(tmp_path):
    pipe, fake, pres, _ = _build(tmp_path, env={})
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-svd", seed=1)
    assert res.outcome == PipelineOutcome.SOCIAL_READY.value
    assert fake.calls[0]["backend_id"] == i2v.BACKEND_ID_SVD_XT_1_1
    assert (fake.calls[0]["settings"].target_width, fake.calls[0]["settings"].target_height) == (1024, 576)
    clip = pres.clips[0]
    assert (clip.width, clip.height, clip.frame_count, clip.fps) == (1024, 576, i2v.DEFAULT_FRAME_COUNT, i2v.DEFAULT_FPS)


def test_wan_22_opt_in_via_env_routes_through_adapter(tmp_path):
    pipe, fake, pres, _ = _build(tmp_path, env={"I2V_BACKEND": "wan_22"})
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-wan", seed=2)
    assert res.outcome == PipelineOutcome.SOCIAL_READY.value
    assert [c["backend_id"] for c in fake.calls] == ["wan_22"]
    s = fake.calls[0]["settings"]
    assert (s.target_width, s.target_height) == (i2v.WAN22_NATIVE_WIDTH, i2v.WAN22_NATIVE_HEIGHT)
    clip = pres.clips[0]
    assert isinstance(clip, pa.RawI2VClipRef)
    assert (clip.width, clip.height) == (720, 1280)
    assert res.presentation_job_id


def test_env_read_at_call_time_from_os_environ(tmp_path, monkeypatch):
    root = tmp_path / "store"
    fake = FakeI2VAdapter(root)
    port = ProductionI2VPort(adapter=fake)  # environ=None -> os.environ
    monkeypatch.delenv("I2V_BACKEND", raising=False)
    assert port.resolve_backend() == "svd_xt_1_1"
    monkeypatch.setenv("I2V_BACKEND", "wan_22")
    assert port.resolve_backend() == "wan_22"


def test_durable_video_path_and_no_identity_canon_propagate(tmp_path):
    pipe, fake, pres, root = _build(tmp_path, env={"I2V_BACKEND": "wan_22"})
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-dur", seed=3)
    clip = pres.clips[0]
    assert Path(clip.video_path).is_file()
    assert Path(root).resolve() in Path(clip.video_path).resolve().parents
    gen = pipe.i2v.result_for(clip.video_sha256)
    assert gen.video_path == clip.video_path and gen.video_path_durable is True
    assert gen.video_creates_identity_canon is False
    assert res.video_creates_identity_canon is False
    assert res.raw_video_sha256 == clip.video_sha256
    assert res.asset_kind == "presented_mp4" and Path(res.asset_path).is_file()


def test_presentation_failure_fails_closed_no_social_ready(tmp_path):
    def boom(clip, transform, out_path):
        raise RuntimeError("render exploded")

    pipe, fake, pres, _ = _build(tmp_path, env={"I2V_BACKEND": "wan_22"}, render=boom)
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-fail", seed=4)
    assert res.outcome != PipelineOutcome.SOCIAL_READY.value
    assert res.asset_kind != "presented_mp4"
    assert res.presented_video_sha256 is None
    assert res.video_creates_identity_canon is False


def test_i2v_non_pass_status_fails_closed(tmp_path):
    pipe, fake, pres, _ = _build(tmp_path, env={})
    fake.status = "INFRA_FAILURE"
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-i2vfail", seed=5)
    assert res.outcome != PipelineOutcome.SOCIAL_READY.value
    assert pres.clips == []


def test_unknown_backend_fails_closed_with_real_adapter(tmp_path):
    pipe = build_default_media_pipeline(tmp_path / "s", environ={"I2V_BACKEND": "bogus_backend"},
                                        render=pa.mock_render, media_validator=_pass_validator)
    res = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-bogus", seed=6)
    assert res.outcome != PipelineOutcome.SOCIAL_READY.value


def test_raw_svd_clip_ref_alias_is_backend_neutral_type():
    assert pa.RawSvdClipRef is pa.RawI2VClipRef
    legacy = pa.RawSvdClipRef(video_path="x.mp4", video_sha256="a" * 64, source_image_sha256="b" * 64)
    assert isinstance(legacy, pa.RawI2VClipRef)
    assert (legacy.width, legacy.height, legacy.frame_count, legacy.fps) == (1024, 576, 25, 6)


def test_clip_ref_defaults_to_svd_geometry_without_result():
    c = clip_ref_from_i2v_result("p.mp4", "a" * 64, "b" * 64, None)
    assert (c.width, c.height) == (pa.SVD_NATIVE_WIDTH, pa.SVD_NATIVE_HEIGHT)
    c2 = clip_ref_from_i2v_result("p.mp4", "a" * 64, "b" * 64,
                                  {"i2v_width": 720, "i2v_height": 1280, "frame_count": 17, "fps": 24})
    assert (c2.width, c2.height, c2.frame_count, c2.fps) == (720, 1280, 17, 24)


def test_default_settings_svd_unchanged():
    assert default_settings_for_backend("svd_xt_1_1") == i2v.I2VSettings()
