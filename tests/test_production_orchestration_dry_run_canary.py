"""CPU tests for PRODUCTION_ORCHESTRATION_DRY_RUN_CANARY control gates.

Live Hermes/GPU are injected; pytest live-barrier forbids network/Comfy, so the
injected live Hermes persists real on-disk prose (non dry-run://) and media is a
real ChapterToMediaWorkflow shape with deterministic ports. Publishing stays dry-run.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from tools.chapter_production_posting_orchestration import VIDEO_CREATES_IDENTITY_CANON, OrchState
from tools.chapter_to_media_workflow import (
    ChapterMediaOutcome,
    ChapterMediaStore,
    ChapterToMediaWorkflow,
    ImageRequestResult,
    ValidatedChapterRef,
)
from tools.media_pipeline_integration import (
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
    _sha256_bytes,
)
from tools.production_orchestration_dry_run_canary import (
    CANARY_VERSION,
    DryRunCanaryRunner,
    LiveHermesAdapter,
    LiveHermesRequired,
    write_live_prose_file,
)
from tools.production_orchestration_live_wiring import (
    LIVE_PUBLISH_ENABLED_DEFAULT,
    SOCIAL_READY_CREATES_IDENTITY_CANON,
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


class CountingMedia(ChapterToMediaWorkflow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    def enqueue_chapter_media(self, chapter, *, seed: int = 0):
        self.calls += 1
        return super().enqueue_chapter_media(chapter, seed=seed)


def _still(tmp_path, payload=b"canary-still"):
    p = tmp_path / "still.png"
    p.write_bytes(payload)
    return ApprovedStillRef(
        image_path=str(p),
        source_image_sha256=_sha256_bytes(payload),
        image_source_approved=True,
    )


def _media(tmp_path, *, fail_i2v: bool = False, awaiting: bool = False):
    ch_store = ChapterMediaStore(tmp_path / "ch_media")
    media_store = MediaRecordStore(tmp_path / "media_store")
    still = _still(tmp_path)
    if awaiting:
        imgs = FakeImageRequests(ImageRequestResult("r-await", still=None, awaiting_approval=True))
        i2v = FakeI2V(FakeI2VResult())
    elif fail_i2v:
        imgs = FakeImageRequests(ImageRequestResult("r1", still=still))
        i2v = FakeI2V(RuntimeError("oom"))
    else:
        vid = tmp_path / "raw.mp4"
        vid.write_bytes(b"raw-video")
        pres = tmp_path / "pres.mp4"
        pres.write_bytes(b"pres-video")
        imgs = FakeImageRequests(ImageRequestResult("r1", still=still))
        i2v = FakeI2V(
            FakeI2VResult(
                video_path=str(vid),
                video_sha256=_sha256_bytes(b"raw-video"),
            )
        )
        presentation = FakePresentation(
            FakePresResult(
                presented_video_path=str(pres),
                presented_video_sha256=_sha256_bytes(b"pres-video"),
            )
        )
        pipe = MediaPipeline(store=media_store, i2v=i2v, presentation=presentation)
        return CountingMedia(store=ch_store, image_requests=imgs, media_pipeline=pipe)

    presentation = FakePresentation(FakePresResult())
    pipe = MediaPipeline(store=media_store, i2v=i2v, presentation=presentation)
    return CountingMedia(store=ch_store, image_requests=imgs, media_pipeline=pipe)


def _live_hermes(root: Path):
    def _gen(*, novel_id: str, chapter_id: str, workflow_id: str):
        body = f"# Canary {chapter_id}\n\nLive Hermes prose for {novel_id} wf={workflow_id}\n"
        return write_live_prose_file(root, novel_id=novel_id, chapter_id=chapter_id, workflow_id=workflow_id, body=body)

    return LiveHermesAdapter(live_generate=_gen)


def test_defaults_safe():
    assert LIVE_PUBLISH_ENABLED_DEFAULT is False
    assert VIDEO_CREATES_IDENTITY_CANON is False
    assert SOCIAL_READY_CREATES_IDENTITY_CANON is False
    assert CANARY_VERSION


def test_refuses_dry_run_hermes_stub(tmp_path):
    from tools.chapter_production_posting_orchestration import ChapterDraft

    def bad(**kwargs):
        return ChapterDraft(
            chapter_id=kwargs["chapter_id"],
            novel_id=kwargs["novel_id"],
            prose_sha256="x",
            body_path="dry-run://nope",
        )

    adapter = LiveHermesAdapter(live_generate=bad)
    with pytest.raises(LiveHermesRequired):
        adapter.generate_prose(novel_id="n", chapter_id="c", workflow_id="w")


def test_canary_happy_path_duplicate_publication_zero(tmp_path):
    media = _media(tmp_path)
    hermes = _live_hermes(tmp_path)
    runner = DryRunCanaryRunner(
        root=tmp_path / "canary",
        chapter_media=media,
        live_hermes=hermes,
        novel_id="novel-a",
        chapter_id="ch-canary-1",
        fiction_id="fiction-1",
        media_call_counter=media,
    )
    report = runner.run(tick_id="t-canary-1", workflow_id="wf-canary-1")
    assert report.gates.ok is True
    assert report.gates.duplicate_publication_count == 0
    assert report.gates.hermes_live_calls >= 1
    assert report.gates.restart_resumed is True
    assert report.gates.live_publish_enabled is False
    assert report.gates.video_creates_identity_canon is False
    assert report.gates.publication_waited_for_video is False
    assert report.gates.patreon_intent_count == 1
    assert report.gates.royal_road_intent_count == 1
    assert report.first["state"] == OrchState.READY.value
    assert report.resumed.get("reused_existing") is True


def test_canary_static_fallback_accepted(tmp_path):
    media = _media(tmp_path, fail_i2v=True)
    hermes = _live_hermes(tmp_path)
    runner = DryRunCanaryRunner(
        root=tmp_path / "canary_sf",
        chapter_media=media,
        live_hermes=hermes,
        novel_id="novel-a",
        chapter_id="ch-sf",
        fiction_id="fiction-1",
        media_call_counter=media,
    )
    report = runner.run(tick_id="t-sf", workflow_id="wf-sf")
    assert report.gates.media_outcome == ChapterMediaOutcome.STATIC_FALLBACK.value
    assert report.gates.static_fallback_accepted is True
    assert report.gates.duplicate_publication_count == 0
    assert report.first["patreon_status"] == "POSTED"
    assert report.first["state"] == OrchState.READY.value


def test_canary_awaiting_approval_publishes_without_waiting_video(tmp_path):
    media = _media(tmp_path, awaiting=True)
    hermes = _live_hermes(tmp_path)
    runner = DryRunCanaryRunner(
        root=tmp_path / "canary_await",
        chapter_media=media,
        live_hermes=hermes,
        novel_id="novel-a",
        chapter_id="ch-await",
        fiction_id="fiction-1",
        media_call_counter=media,
    )
    report = runner.run(tick_id="t-await", workflow_id="wf-await")
    assert report.gates.publication_waited_for_video is False
    assert report.gates.media_outcome == ChapterMediaOutcome.AWAITING_APPROVAL.value
    assert report.first["patreon_status"] == "POSTED"
    assert report.gates.duplicate_publication_count == 0
