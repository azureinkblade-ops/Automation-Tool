"""Steps 4-5: identity cutoff and TikTok hold semantics."""

from __future__ import annotations

from datetime import datetime
from tools.weekday_cadence import timezone_for
from tools.weekday_cadence_posts import apply_media_required_holds

from tools.weekday_cadence import (
    CadenceItem,
    apply_identity_cutoff,
    approval_deadline_for,
    apply_x_default,
)
from tools.weekday_cadence_config import WeekdayCadenceConfig
from tools.weekday_cadence_posts import ClipResult, evaluate_tiktok_clip


TZ = timezone_for("America/Phoenix")
CFG = WeekdayCadenceConfig()


def _item(status="ready", platform="tiktok", **kwargs) -> CadenceItem:
    data = dict(
        id=f"EN-{platform}",
        platform=platform,
        novel="EN",
        source_chapter=138,
        source_platform="patreon",
        caption="caption",
        media=[],
        status=status,
        hold_reason=None,
        posted_url="",
        posted_at="",
    )
    data.update(kwargs)
    return CadenceItem(**data)


def test_approval_deadline_is_6pm_previous_evening():
    deadline = approval_deadline_for("2026-11-23", CFG)
    assert deadline.tzinfo is not None
    assert deadline.isoformat() == "2026-11-22T18:00:00-07:00"


def test_unapproved_identity_before_deadline_awaits_approval():
    now = datetime(2026, 11, 22, 16, 0, tzinfo=TZ)
    item = apply_identity_cutoff(
        _item(),
        needs_approval=True,
        approved=False,
        now=now,
        deadline=approval_deadline_for("2026-11-23", CFG),
    )
    assert item.status == "awaiting_approval"
    assert item.hold_reason is None


def test_unapproved_identity_after_deadline_is_held():
    now = datetime(2026, 11, 22, 18, 1, tzinfo=TZ)
    item = apply_identity_cutoff(
        _item(),
        needs_approval=True,
        approved=False,
        now=now,
        deadline=approval_deadline_for("2026-11-23", CFG),
    )
    assert item.status == "held"
    assert item.hold_reason == "IDENTITY_UNAPPROVED"


def test_approved_identity_does_not_block():
    now = datetime(2026, 11, 22, 19, 0, tzinfo=TZ)
    item = apply_identity_cutoff(
        _item(),
        needs_approval=True,
        approved=True,
        now=now,
        deadline=approval_deadline_for("2026-11-23", CFG),
    )
    assert item.status == "ready"


def test_x_defaults_to_awaiting_david_post():
    item = apply_x_default(_item(platform="x", status="ready"), CFG)
    assert item.status == "awaiting_david_post"
    held = apply_x_default(_item(platform="x", status="held", hold_reason="CHAPTER_SOURCE_UNVERIFIED:patreon"), CFG)
    assert held.status == "held"


def test_wan_social_ready_clip_with_passing_probe_is_ready():
    clip = ClipResult(
        outcome="SOCIAL_READY",
        backend="wan_22",
        frame_count=73,
        duration_seconds=3.04,
        width=1080,
        height=1920,
    )
    status, reason = evaluate_tiktok_clip(clip, config=CFG)
    assert status == "ready"
    assert reason is None


def test_svd_slideshow_and_failed_probe_are_held():
    svd = ClipResult(outcome="SOCIAL_READY", backend="svd_xt_1_1", social_hold=True, hold_reason="SVD_FALLBACK_SOCIAL_HOLD")
    status, reason = evaluate_tiktok_clip(svd, config=CFG)
    assert status == "held"
    assert reason == "SVD_FALLBACK_SOCIAL_HOLD"

    slideshow = ClipResult(outcome="SOCIAL_READY", backend="wan_22", kind="slideshow", frame_count=73, duration_seconds=20, width=1080, height=1920)
    status, reason = evaluate_tiktok_clip(slideshow, config=CFG)
    assert status == "held"
    assert "slideshow" in (reason or "")

    bad = ClipResult(outcome="SOCIAL_READY", backend="wan_22", frame_count=72, duration_seconds=3.0, width=1080, height=1920)
    status, reason = evaluate_tiktok_clip(bad, config=CFG)
    assert status == "held"
    assert reason == "MEDIA_HOLD:FRAME_PROBE_FAILED"


def test_facebook_and_instagram_without_media_are_never_ready():
    fb = _item(status="ready", platform="facebook")
    ig = _item(status="ready", platform="instagram")
    x = _item(status="awaiting_david_post", platform="x")
    ready = _item(status="ready", platform="facebook", media=["media/EN-still.png"])
    already_held = _item(status="held", platform="instagram", hold_reason="CHAPTER_SOURCE_UNVERIFIED:patreon")
    apply_media_required_holds([fb, ig, x, ready, already_held])
    assert fb.status == "held"
    assert fb.hold_reason == "MEDIA_REQUIRED_MISSING"
    assert ig.status == "held"
    assert ig.hold_reason == "MEDIA_REQUIRED_MISSING"
    assert x.status == "awaiting_david_post"
    assert ready.status == "ready"
    assert already_held.status == "held"
    assert already_held.hold_reason == "CHAPTER_SOURCE_UNVERIFIED:patreon"
