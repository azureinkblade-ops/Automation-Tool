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
    assert item.hold_reason == "IDENTITY_AWAITING_APPROVAL"


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
    assert item.hold_reason == "AWAITING_DAVID_POST"
    held = apply_x_default(_item(platform="x", status="held", hold_reason="CHAPTER_SOURCE_UNVERIFIED:patreon"), CFG)
    assert held.status == "held"
    assert held.hold_reason == "CHAPTER_SOURCE_UNVERIFIED:patreon"


def test_x_is_never_identity_gated():
    from datetime import datetime
    from tools.weekday_cadence import apply_depiction_gate, ensure_hold_reasons, timezone_for

    tz = timezone_for("America/Phoenix")
    now = datetime(2026, 11, 22, 16, 0, tzinfo=tz)
    deadline = approval_deadline_for("2026-11-23", CFG)
    item = _item(platform="x", status="ready", depiction="governed")
    item = apply_depiction_gate(item, approved=False, now=now, deadline=deadline)
    item = apply_x_default(item, CFG)
    assert item.status == "awaiting_david_post"
    assert item.hold_reason == "AWAITING_DAVID_POST"
    ensure_hold_reasons([item])
    assert item.hold_reason == "AWAITING_DAVID_POST"


def test_depiction_gate_three_branches():
    from datetime import datetime
    from tools.weekday_cadence import apply_depiction_gate, timezone_for

    tz = timezone_for("America/Phoenix")
    now = datetime(2026, 11, 22, 16, 0, tzinfo=tz)
    deadline = approval_deadline_for("2026-11-23", CFG)

    governed = apply_depiction_gate(
        _item(platform="facebook", status="ready", media=["media/en.png"], depiction="governed"),
        approved=False, now=now, deadline=deadline,
    )
    assert governed.status == "awaiting_approval"
    assert governed.hold_reason == "IDENTITY_AWAITING_APPROVAL"
    assert governed.media == ["media/en.png"]

    clear = apply_depiction_gate(
        _item(platform="facebook", status="ready", media=["media/sf.png"], depiction="not_governed"),
        approved=False, now=now, deadline=deadline,
    )
    assert clear.status == "ready"
    assert clear.hold_reason is None

    unknown = apply_depiction_gate(
        _item(platform="instagram", status="ready", depiction="unknown"),
        approved=False, now=now, deadline=deadline,
    )
    assert unknown.status == "awaiting_approval"
    assert unknown.hold_reason == "NO_STRUCTURED_DEPICTION_EVIDENCE"


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


def test_gray_hand_items_are_held_fail_closed():
    from tools.weekday_cadence import apply_gray_look_hold, shows_undecided_gray_hand
    from tools.weekday_cadence_config import HOLD_GRAY_LOOK_UNDECIDED, STATUS_AWAITING_APPROVAL, STATUS_READY
    from tools.weekday_cadence_manifest import CadenceItem

    cases = [
        (
            "tiktok",
            "SF",
            117,
            "A marked palm held up to the snow, three narrow glowing bars across it, a burning sanctuary blurred behind.",
            True,
        ),
        (
            "facebook",
            "SF",
            117,
            "Lisern holding a marked hand in both of hers, the light under her skin dimming where they touch.",
            True,
        ),
        (
            "instagram",
            "SF",
            117,
            "Lisern holding a marked hand in both of hers, the light under her skin dimming where they touch.",
            True,
        ),
        (
            "facebook",
            "SF",
            124,
            "A small child taking an unmarked hand at the edge of a glowing forge-heart.",
            True,
        ),
        (
            "instagram",
            "SF",
            124,
            "A small child taking an unmarked hand at the edge of a glowing forge-heart.",
            True,
        ),
        (
            "tiktok",
            "SF",
            124,
            "A deep furnace node under a market, its flame folding inward, frost spreading over the stone above.",
            False,
        ),
        (
            "tiktok",
            "SF",
            117,
            "Ancient towers rising out of a mountainside, furnaces opening along their faces like burning eyes, snow turning to ash.",
            False,
        ),
        (
            "facebook",
            "SF",
            117,
            "A sanctuary terrace at night, every roof burning, snow falling into ash above it.",
            False,
        ),
        (
            "x",
            "SF",
            117,
            "A marked palm held up to the snow, three narrow glowing bars across it.",
            False,
        ),
        (
            "facebook",
            "EN",
            127,
            "A marked palm held up to the snow.",
            False,
        ),
    ]
    held_ids = []
    for platform, novel, chapter, visual, expect in cases:
        item = CadenceItem(
            id=f"{novel}-{platform}",
            platform=platform,
            novel=novel,
            source_chapter=chapter,
            source_platform="patreon",
            caption=f"{novel} chapter {chapter}",
            visual=visual,
            depiction="not_governed",
            status=STATUS_READY,
        )
        assert shows_undecided_gray_hand(item) is expect
        apply_gray_look_hold(item)
        if expect:
            assert item.status == STATUS_AWAITING_APPROVAL
            assert item.hold_reason == HOLD_GRAY_LOOK_UNDECIDED
            held_ids.append(f"{novel}-{chapter}-{platform}")
        else:
            assert item.hold_reason != HOLD_GRAY_LOOK_UNDECIDED
            assert item.status == STATUS_READY
    assert held_ids == [
        "SF-117-tiktok",
        "SF-117-facebook",
        "SF-117-instagram",
        "SF-124-facebook",
        "SF-124-instagram",
    ]
