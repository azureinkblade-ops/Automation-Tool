"""CPU tests: video-required media fails closed to MEDIA_HOLD (never static-as-success).

No GPU / no ComfyUI: all I2V / presentation ports are fakes; the pytest live barrier
denies network and Comfy access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pytest

from tools.chapter_production_posting_orchestration import (
    BacklogItem,
    ChapterDraft,
    ChapterProductionPostingOrchestrator,
    OrchState,
    OrchStore,
    PublishResult,
    SocialPostResult,
    ValidationResult,
)
from tools.chapter_to_media_workflow import (
    ChapterMediaOutcome,
    ChapterMediaState,
    ChapterMediaStore,
    ChapterToMediaWorkflow,
    ImageRequestResult,
    ValidatedChapterRef,
)
from tools.comfy_http_i2v_transport import ComfyTransportUnavailable
from tools.media_pipeline_integration import (
    MEDIA_HOLD_REASON_PREFIX,
    ApprovedStillRef,
    MediaPipeline,
    MediaRecordStore,
    PipelineOutcome,
    PipelineState,
    _sha256_bytes,
)
from tools.media_validity import MEDIA_VALIDITY_PREFIX, pass_probe_for_tests, validate_presented_social_video


def _pass_validator(path, **kwargs):
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


def _still(tmp_path, payload=b"approved-still"):
    p = tmp_path / "still.png"
    p.write_bytes(payload)
    return ApprovedStillRef(image_path=str(p), source_image_sha256=_sha256_bytes(payload), image_source_approved=True)


def _good_pres(tmp_path):
    presented = tmp_path / "pres.mp4"
    presented.write_bytes(b"presented-9x16")
    return FakePresentation(
        FakePresResult(presented_video_path=str(presented), presented_video_sha256=_sha256_bytes(b"presented-9x16"))
    )


def _raw(tmp_path, payload=b"raw-svd"):
    raw = tmp_path / "raw.mp4"
    raw.write_bytes(payload)
    return raw


def _pipe(tmp_path, i2v, pres=None, **kw):
    return MediaPipeline(
        store=MediaRecordStore(tmp_path / "media_store"),
        i2v=i2v,
        presentation=pres or _good_pres(tmp_path),
        media_validator=_pass_validator,
        **kw,
    )


def _assert_held(result, why_prefix: str):
    assert result.outcome == PipelineOutcome.MEDIA_HOLD.value
    assert result.state == PipelineState.MEDIA_HOLD.value
    assert result.outcome not in {PipelineOutcome.SOCIAL_READY.value, PipelineOutcome.STATIC_FALLBACK.value}
    assert result.asset_path is None and result.asset_sha256 is None
    assert result.asset_kind == "none"
    assert result.failure_reason.startswith(f"{MEDIA_HOLD_REASON_PREFIX}:{why_prefix}")


# --- pipeline level ---------------------------------------------------------


def test_comfy_unreachable_is_hold_not_success(tmp_path):
    i2v = FakeI2V(ComfyTransportUnavailable("connection refused 127.0.0.1:8188"))
    pres = _good_pres(tmp_path)
    r = _pipe(tmp_path, i2v, pres).produce_social_media(_still(tmp_path), workflow_id="wf-comfy-down", seed=1)
    _assert_held(r, "i2v_failed:")
    assert "connection refused" in r.failure_reason
    assert pres.calls == 0


def test_infra_failure_status_is_hold(tmp_path):
    i2v = FakeI2V(FakeI2VResult(validation_status="INFRA_FAILURE"))
    r = _pipe(tmp_path, i2v).produce_social_media(_still(tmp_path), workflow_id="wf-infra", seed=1)
    _assert_held(r, "i2v_failed:i2v_status=INFRA_FAILURE")


def test_timeout_is_hold(tmp_path):
    i2v = FakeI2V(TimeoutError("i2v poll timed out"))
    r = _pipe(tmp_path, i2v).produce_social_media(_still(tmp_path), workflow_id="wf-timeout", seed=1)
    _assert_held(r, "i2v_failed:")


@pytest.mark.parametrize("status", ["PARTIAL", "VIDEO_REVIEW_REQUIRED"])
def test_review_status_is_hold(tmp_path, status):
    raw = _raw(tmp_path)
    i2v = FakeI2V(FakeI2VResult(validation_status=status, video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = _good_pres(tmp_path)
    r = _pipe(tmp_path, i2v, pres).produce_social_media(_still(tmp_path), workflow_id=f"wf-{status}", seed=2)
    _assert_held(r, f"i2v_review_required:{status}")
    assert r.raw_video_sha256 == _sha256_bytes(b"raw-svd")  # kept for review
    assert pres.calls == 0


def test_empty_video_file_is_hold(tmp_path):
    raw = _raw(tmp_path, b"")
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"")))
    pres = _good_pres(tmp_path)
    r = _pipe(tmp_path, i2v, pres).produce_social_media(_still(tmp_path), workflow_id="wf-empty", seed=3)
    _assert_held(r, "i2v_failed:i2v video file empty")
    assert pres.calls == 0


def test_missing_video_file_is_hold(tmp_path):
    i2v = FakeI2V(FakeI2VResult(video_path=str(tmp_path / "nope.mp4"), video_sha256="a" * 64))
    r = _pipe(tmp_path, i2v).produce_social_media(_still(tmp_path), workflow_id="wf-missing", seed=3)
    _assert_held(r, "i2v_failed:i2v video file missing")


def test_missing_video_sha_is_hold(tmp_path):
    raw = _raw(tmp_path)
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=None))
    r = _pipe(tmp_path, i2v).produce_social_media(_still(tmp_path), workflow_id="wf-nosha", seed=3)
    _assert_held(r, "i2v_failed:i2v missing video_sha256")


def test_invalid_presented_video_is_hold(tmp_path):
    raw = _raw(tmp_path)
    presented = tmp_path / "tiny.mp4"
    presented.write_bytes(b"x" * 158)
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = FakePresentation(FakePresResult(presented_video_path=str(presented), presented_video_sha256=_sha256_bytes(b"x" * 158)))
    pipe = MediaPipeline(store=MediaRecordStore(tmp_path / "ms"), i2v=i2v, presentation=pres)  # default validator
    r = pipe.produce_social_media(_still(tmp_path), workflow_id="wf-tiny", seed=3)
    _assert_held(r, f"{MEDIA_VALIDITY_PREFIX}:too_small")


def test_hold_is_not_reused_and_retries(tmp_path):
    i2v = FakeI2V(ComfyTransportUnavailable("down"))
    pipe = _pipe(tmp_path, i2v)
    still = _still(tmp_path)
    a = pipe.produce_social_media(still, workflow_id="wf-retry", seed=4)
    assert a.outcome == PipelineOutcome.MEDIA_HOLD.value
    # ComfyUI back: same workflow/seed retries I2V instead of reusing the hold
    raw = _raw(tmp_path)
    i2v.result = FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd"))
    b = pipe.produce_social_media(still, workflow_id="wf-retry", seed=4)
    assert b.reused_existing is False
    assert i2v.calls == 2
    assert b.outcome == PipelineOutcome.SOCIAL_READY.value


def test_valid_clip_social_ready_unchanged(tmp_path):
    raw = _raw(tmp_path)
    i2v = FakeI2V(FakeI2VResult(video_path=str(raw), video_sha256=_sha256_bytes(b"raw-svd")))
    pres = _good_pres(tmp_path)
    r = _pipe(tmp_path, i2v, pres).produce_social_media(_still(tmp_path), workflow_id="wf-ok", seed=5)
    assert r.outcome == PipelineOutcome.SOCIAL_READY.value
    assert r.state == PipelineState.READY.value
    assert r.asset_kind == "presented_mp4"
    assert r.asset_sha256 == _sha256_bytes(b"presented-9x16")
    assert r.failure_reason is None
    assert i2v.calls == 1 and pres.calls == 1


def test_video_not_required_keeps_legacy_static_fallback(tmp_path):
    still = _still(tmp_path)
    r = _pipe(tmp_path, FakeI2V(RuntimeError("oom")), video_required=False).produce_social_media(
        still, workflow_id="wf-legacy", seed=6
    )
    assert r.outcome == PipelineOutcome.STATIC_FALLBACK.value
    assert r.asset_kind == "static_still"
    assert r.asset_sha256 == still.source_image_sha256
    assert r.failure_reason == "i2v_failed:oom"


# --- chapter media workflow ---------------------------------------------------


def _chapter(wf):
    return ValidatedChapterRef(chapter_id="ch-1", novel_id="n1", workflow_id=wf)


def test_chapter_media_hold_not_ready(tmp_path):
    ch_store = ChapterMediaStore(tmp_path / "ch")
    pipe = _pipe(tmp_path, FakeI2V(ComfyTransportUnavailable("down")))
    wf = ChapterToMediaWorkflow(
        store=ch_store,
        image_requests=FakeImageRequests(ImageRequestResult("req-h", still=_still(tmp_path))),
        media_pipeline=pipe,
    )
    r = wf.enqueue_chapter_media(_chapter("wf-ch-hold"), seed=1)
    assert r.outcome == ChapterMediaOutcome.MEDIA_HOLD.value
    assert r.state == ChapterMediaState.MEDIA_HOLD.value
    assert r.media_outcome == PipelineOutcome.MEDIA_HOLD.value
    assert r.media_hold is True
    assert r.asset_path is None and r.asset_sha256 is None and r.asset_kind is None
    assert r.failure_reason.startswith(f"{MEDIA_HOLD_REASON_PREFIX}:i2v_failed:")
    rec = ch_store.get(r.idempotency_key)
    assert ch_store.verify_ready_asset(rec) is False


def test_image_only_awaiting_approval_unchanged(tmp_path):
    i2v = FakeI2V(FakeI2VResult())
    wf = ChapterToMediaWorkflow(
        store=ChapterMediaStore(tmp_path / "ch"),
        image_requests=FakeImageRequests(ImageRequestResult("req-a", awaiting_approval=True)),
        media_pipeline=_pipe(tmp_path, i2v),
    )
    r = wf.enqueue_chapter_media(_chapter("wf-await"), seed=1)
    assert r.outcome == ChapterMediaOutcome.AWAITING_APPROVAL.value
    assert r.awaiting_approval is True
    assert r.media_hold is False
    assert i2v.calls == 0


# --- orchestration: held media is never posted ------------------------------


class _Hermes:
    def generate_prose(self, *, novel_id, chapter_id, workflow_id):
        return ChapterDraft(chapter_id=chapter_id, novel_id=novel_id, prose_sha256="p", body_path=f"/tmp/{chapter_id}.md")


class _Validator:
    def validate(self, draft):
        return ValidationResult(ok=True, validation_status="VALIDATED")


class _Store:
    def store_validated(self, draft, validation):
        return f"store-{draft.chapter_id}"


class _Backlog:
    def __init__(self, items: List[BacklogItem]):
        self.items = items

    def list_backlog(self):
        return list(self.items)


class _Post:
    def __init__(self, channel):
        self.channel = channel
        self.calls = 0

    def post_chapter(self, *, novel_id, chapter_id, store_id, idempotency_key, remote_fiction_id=None):
        self.calls += 1
        return PublishResult(channel=self.channel, remote_id=f"{self.channel}-1", idempotency_key=idempotency_key, status="POSTED")


class _Social:
    def __init__(self):
        self.calls = 0

    def post_social(self, **kwargs):
        self.calls += 1
        return SocialPostResult(status="POSTED", asset_kind=kwargs.get("asset_kind"), asset_sha256=kwargs.get("asset_sha256"))


def test_orchestration_never_posts_held_media(tmp_path):
    media = ChapterToMediaWorkflow(
        store=ChapterMediaStore(tmp_path / "ch"),
        image_requests=FakeImageRequests(ImageRequestResult("req-o", still=_still(tmp_path))),
        media_pipeline=_pipe(tmp_path, FakeI2V(ComfyTransportUnavailable("down"))),
    )
    social = _Social()
    orch = ChapterProductionPostingOrchestrator(
        store=OrchStore(tmp_path / "orch"),
        hermes=_Hermes(),
        validator=_Validator(),
        chapter_store=_Store(),
        patreon_backlog=_Backlog([BacklogItem(chapter_id="ch-1", novel_id="n1", channel="patreon", priority=1)]),
        patreon_post=_Post("patreon"),
        royal_road_post=_Post("royal_road"),
        social_post=social,
        chapter_media=media,
        royal_road_fiction_id_for=lambda n: f"f-{n}",
        next_inventory_chapter=lambda: None,
    )
    r = orch.run_tick(tick_id="t-hold", workflow_id="wf-hold")
    assert r.media_outcome == ChapterMediaOutcome.MEDIA_HOLD.value
    assert r.media_asset_kind is None
    assert r.social_status == "HELD_MEDIA"
    assert social.calls == 0  # still image is never posted in place of the clip
    assert (r.failure_reason or "").startswith(f"{MEDIA_HOLD_REASON_PREFIX}:")
    assert r.state == OrchState.READY.value