"""CPU/mock tests for CHAPTER_TO_MEDIA_WORKFLOW_INTEGRATION."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from tools.chapter_to_media_workflow import (
    ChapterMediaOutcome,
    ChapterMediaState,
    ChapterMediaStore,
    ChapterToMediaWorkflow,
    ImageRequestResult,
    ValidatedChapterRef,
)
from tools.media_pipeline_integration import (
    VIDEO_CREATES_IDENTITY_CANON,
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
    _sha256_bytes,
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


class FakeImageRequests:
    def __init__(self, result: ImageRequestResult):
        self.result = result
        self.calls = 0

    def request_approved_still(self, chapter, *, workflow_id: str):
        self.calls += 1
        return self.result


def _chapter(wf="wf-ch-1"):
    return ValidatedChapterRef(chapter_id="ch-1", novel_id="novel-a", workflow_id=wf)


def _still(tmp_path, payload=b"approved-still"):
    p = tmp_path / "still.png"
    p.write_bytes(payload)
    return ApprovedStillRef(image_path=str(p), source_image_sha256=_sha256_bytes(payload), image_source_approved=True)


@pytest.fixture
def stores(tmp_path):
    return ChapterMediaStore(tmp_path / "ch_store"), MediaRecordStore(tmp_path / "media_store")


def test_rejects_unvalidated_chapter(stores, tmp_path):
    ch_store, media_store = stores
    pipe = MediaPipeline(store=media_store, i2v=FakeI2V(FakeI2VResult()), presentation=FakePresentation(FakePresResult()))
    wf = ChapterToMediaWorkflow(store=ch_store, image_requests=FakeImageRequests(ImageRequestResult("r1")), media_pipeline=pipe)
    with pytest.raises(ValueError):
        wf.enqueue_chapter_media(ValidatedChapterRef(chapter_id="c", novel_id="n", validation_status="DRAFT"))


def test_happy_path_social_ready(stores, tmp_path):
    ch_store, media_store = stores
    still = _still(tmp_path)
    raw = tmp_path / "raw.mp4"; raw.write_bytes(b"raw")
    presented = tmp_path / "p.mp4"; presented.write_bytes(b"pres")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw")))
    pres = FakePresentation(FakePresResult(presented_video_path=str(presented), presented_video_sha256=_sha256_bytes(b"pres")))
    pipe = MediaPipeline(store=media_store, i2v=i2v, presentation=pres)
    imgs = FakeImageRequests(ImageRequestResult("req-1", still=still))
    wf = ChapterToMediaWorkflow(store=ch_store, image_requests=imgs, media_pipeline=pipe)
    result = wf.enqueue_chapter_media(_chapter(), seed=1)
    assert result.outcome == ChapterMediaOutcome.SOCIAL_READY.value
    assert result.state == ChapterMediaState.READY.value
    assert result.video_creates_identity_canon is False
    assert result.publishing_wired is False
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert imgs.calls == 1 and i2v.calls == 1


def test_static_fallback_is_nonblocking_ready(stores, tmp_path):
    ch_store, media_store = stores
    still = _still(tmp_path)
    pipe = MediaPipeline(store=media_store, i2v=FakeI2V(RuntimeError("oom")), presentation=FakePresentation(FakePresResult()))
    wf = ChapterToMediaWorkflow(
        store=ch_store,
        image_requests=FakeImageRequests(ImageRequestResult("req-2", still=still)),
        media_pipeline=pipe,
    )
    result = wf.enqueue_chapter_media(_chapter("wf-fb"), seed=2)
    assert result.outcome == ChapterMediaOutcome.STATIC_FALLBACK.value
    assert result.state == ChapterMediaState.READY_STATIC_FALLBACK.value
    assert result.asset_kind == "static_still"
    # Not FAILED — chapter media enqueue succeeds with static
    assert result.state != ChapterMediaState.FAILED.value


def test_awaiting_approval_does_not_run_media(stores, tmp_path):
    ch_store, media_store = stores
    i2v = FakeI2V(FakeI2VResult())
    pipe = MediaPipeline(store=media_store, i2v=i2v, presentation=FakePresentation(FakePresResult()))
    wf = ChapterToMediaWorkflow(
        store=ch_store,
        image_requests=FakeImageRequests(ImageRequestResult("req-3", awaiting_approval=True)),
        media_pipeline=pipe,
    )
    result = wf.enqueue_chapter_media(_chapter("wf-await"), seed=3)
    assert result.awaiting_approval is True
    assert result.outcome == ChapterMediaOutcome.AWAITING_APPROVAL.value
    assert i2v.calls == 0


def test_idempotent_reuse(stores, tmp_path):
    ch_store, media_store = stores
    still = _still(tmp_path)
    raw = tmp_path / "raw.mp4"; raw.write_bytes(b"raw")
    presented = tmp_path / "p.mp4"; presented.write_bytes(b"pres")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw")))
    pipe = MediaPipeline(
        store=media_store,
        i2v=i2v,
        presentation=FakePresentation(FakePresResult(presented_video_path=str(presented), presented_video_sha256=_sha256_bytes(b"pres"))),
    )
    imgs = FakeImageRequests(ImageRequestResult("req-4", still=still))
    wf = ChapterToMediaWorkflow(store=ch_store, image_requests=imgs, media_pipeline=pipe)
    a = wf.enqueue_chapter_media(_chapter("wf-id"), seed=4)
    b = wf.enqueue_chapter_media(_chapter("wf-id"), seed=4)
    assert b.reused_existing is True
    assert imgs.calls == 1 and i2v.calls == 1
