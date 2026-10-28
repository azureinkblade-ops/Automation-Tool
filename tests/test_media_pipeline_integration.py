"""CPU/mock tests for MEDIA_PIPELINE_INTEGRATION."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from tools.media_pipeline_integration import (
    VIDEO_CREATES_IDENTITY_CANON,
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
    PipelineOutcome,
    PipelineState,
    _sha256_bytes,
)
from tools.media_validity import pass_probe_for_tests, validate_presented_social_video


def _pass_validator(path, **kwargs):
    """Existing unit fixtures are tiny byte tags — inject probe so validity can pass."""
    kw = dict(kwargs)
    kw["min_bytes"] = 1
    return validate_presented_social_video(path, probe_fn=pass_probe_for_tests(), **kw)


@dataclass
class FakeI2VResult:
    validation_status: str = "PASS"
    video_path: Optional[str] = None
    video_sha256: Optional[str] = None
    video_job_id: str = "i2v-1"


@dataclass
class FakePresResult:
    validation_status: str = "PASS"
    presented_video_path: Optional[str] = None
    presented_video_sha256: Optional[str] = None
    presentation_job_id: str = "pres-1"


class FakeI2V:
    def __init__(self, result: FakeI2VResult | Exception):
        self.result = result
        self.calls = 0

    def generate_video(self, still, *, seed: int, workflow_id: str):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePresentation:
    def __init__(self, result: FakePresResult | Exception):
        self.result = result
        self.calls = 0

    def present_video(self, raw_video_path, video_sha256, source_image_sha256, *, workflow_id: str):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def store(tmp_path):
    return MediaRecordStore(tmp_path / "media_store")


def _still(tmp_path, payload=b"approved-still"):
    p = tmp_path / "still.png"
    p.write_bytes(payload)
    return ApprovedStillRef(
        image_path=str(p),
        source_image_sha256=_sha256_bytes(payload),
        image_source_approved=True,
    )


def test_happy_path_social_ready(store, tmp_path):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw-svd")
    presented = tmp_path / "pres.mp4"
    presented.write_bytes(b"presented-9x16")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = FakePresentation(
        FakePresResult(
            presented_video_path=str(presented),
            presented_video_sha256=_sha256_bytes(b"presented-9x16"),
        )
    )
    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres, media_validator=_pass_validator)
    result = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-1", seed=1)
    assert result.outcome == PipelineOutcome.SOCIAL_READY.value
    assert result.state == PipelineState.READY.value
    assert result.asset_kind == "presented_mp4"
    assert result.video_creates_identity_canon is False
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert i2v.calls == 1 and pres.calls == 1


def test_i2v_failure_falls_back_to_static(store, tmp_path):
    i2v = FakeI2V(RuntimeError("oom"))
    pres = FakePresentation(FakePresResult())
    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres, media_validator=_pass_validator)
    still = _still(tmp_path)
    result = pipe.produce_social_media(still, workflow_id="wf-fb-i2v", seed=2)
    assert result.outcome == PipelineOutcome.STATIC_FALLBACK.value
    assert result.asset_kind == "static_still"
    assert result.asset_sha256 == still.source_image_sha256
    assert pres.calls == 0


def test_presentation_failure_falls_back_to_static(store, tmp_path):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw-svd")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = FakePresentation(RuntimeError("ffmpeg"))
    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres, media_validator=_pass_validator)
    still = _still(tmp_path)
    result = pipe.produce_social_media(still, workflow_id="wf-fb-pres", seed=3)
    assert result.outcome == PipelineOutcome.STATIC_FALLBACK.value
    assert result.asset_kind == "static_still"
    assert "presentation_failed" in (result.failure_reason or "")


def test_idempotent_reuse_hash_gated(store, tmp_path):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw-svd")
    presented = tmp_path / "pres.mp4"
    presented.write_bytes(b"presented-9x16")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = FakePresentation(
        FakePresResult(
            presented_video_path=str(presented),
            presented_video_sha256=_sha256_bytes(b"presented-9x16"),
        )
    )
    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres, media_validator=_pass_validator)
    still = _still(tmp_path)
    a = pipe.produce_social_media(still, workflow_id="wf-id", seed=4)
    b = pipe.produce_social_media(still, workflow_id="wf-id", seed=4)
    assert b.reused_existing is True
    assert i2v.calls == 1
    presented.write_bytes(b"CORRUPT")
    c = pipe.produce_social_media(still, workflow_id="wf-id", seed=4)
    assert c.reused_existing is False
    assert i2v.calls == 2


def test_unapproved_still_rejected(store, tmp_path):
    still = _still(tmp_path)
    still.image_source_approved = False
    pipe = MediaPipeline(store=store, i2v=FakeI2V(FakeI2VResult()), presentation=FakePresentation(FakePresResult()), media_validator=_pass_validator)
    with pytest.raises(ValueError):
        pipe.produce_social_media(still, workflow_id="wf-unapp", seed=5)
