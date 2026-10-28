"""Media validity gates before SOCIAL_READY."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from tools.media_pipeline_integration import (
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
    PipelineOutcome,
    PipelineState,
    _sha256_bytes,
)
from tools.media_validity import (
    MEDIA_VALIDITY_PREFIX,
    pass_probe_for_tests,
    validate_presented_social_video,
)


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
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate_video(self, still, *, seed: int, workflow_id: str):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePresentation:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def present_video(self, raw_video_path, video_sha256, source_image_sha256, *, workflow_id: str):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _still(tmp_path, payload=b"approved-still"):
    p = tmp_path / "still.png"
    p.write_bytes(payload)
    return ApprovedStillRef(
        image_path=str(p),
        source_image_sha256=_sha256_bytes(payload),
        image_source_approved=True,
    )


def test_158b_fake_mp4_not_social_ready(tmp_path):
    store = MediaRecordStore(tmp_path / "store")
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw-svd-bytes")
    presented = tmp_path / "pres.mp4"
    presented.write_bytes(b"x" * 158)
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd-bytes")))
    pres = FakePresentation(
        FakePresResult(
            presented_video_path=str(presented),
            presented_video_sha256=_sha256_bytes(b"x" * 158),
        )
    )
    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres)
    result = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-tiny", seed=1)
    assert result.outcome != PipelineOutcome.SOCIAL_READY.value
    assert result.outcome == PipelineOutcome.STATIC_FALLBACK.value
    assert result.state == PipelineState.STATIC_FALLBACK.value
    assert (result.failure_reason or "").startswith(f"{MEDIA_VALIDITY_PREFIX}:too_small")


def test_valid_mocked_probe_allows_social_ready(tmp_path):
    store = MediaRecordStore(tmp_path / "store")
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(b"raw-svd-bytes")
    presented = tmp_path / "pres.mp4"
    presented.write_bytes(b"y" * 12_000)
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd-bytes")))
    pres = FakePresentation(
        FakePresResult(
            presented_video_path=str(presented),
            presented_video_sha256=_sha256_bytes(b"y" * 12_000),
        )
    )

    def _validator(path, **kwargs):
        return validate_presented_social_video(path, probe_fn=pass_probe_for_tests(), **kwargs)

    pipe = MediaPipeline(store=store, i2v=i2v, presentation=pres, media_validator=_validator)
    result = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-ok", seed=2)
    assert result.outcome == PipelineOutcome.SOCIAL_READY.value
    assert result.state == PipelineState.READY.value
    assert result.failure_reason is None


def test_validate_helper_too_small_direct(tmp_path):
    p = tmp_path / "t.mp4"
    p.write_bytes(b"z" * 158)
    r = validate_presented_social_video(p)
    assert r.ok is False
    assert r.failure_reason == f"{MEDIA_VALIDITY_PREFIX}:too_small"
