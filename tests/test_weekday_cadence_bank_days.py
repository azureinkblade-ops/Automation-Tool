"""Bank-day rotation: date mapping, recent-live preemption, supplement days, fallbacks."""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

from tools.weekday_cadence_bank_days import (
    RULE_BANK_DAY,
    RULE_GENERATED,
    RULE_NEWEST_FALLBACK,
    RULE_RECENT_LIVE,
    RULE_SUPPLEMENT_DAY,
    bank_day_for,
    choose_for_platform,
    cycle_length_for_novel,
    is_recent_live,
    supplement_chapters_in_file_order,
    weekday_offset,
)
from tools.weekday_cadence_captions import parse_copy_bank, select_bank_caption
from tools.weekday_cadence_config import BANK_DAY_START, WeekdayCadenceConfig


BANK = """
## Day 1 (Week 1, Monday)
### EN: Eternal Nexus
**TikTok** [source EN-127]
- Caption: Day 1 tiktok EN-127.
**FB/IG post** [source EN-127]
- Text: Day 1 facebook EN-127.
**X post** [source EN-127]
day 1 x EN-127

## Day 2 (Week 1, Tuesday)
### EN: Eternal Nexus
**TikTok** [source EN-128]
- Caption: Day 2 tiktok EN-128.
**FB/IG post** [source EN-128]
- Text: Day 2 facebook EN-128.
**X post** [source EN-128]
day 2 x EN-128

## Supplement: newly confirmed live chapters (EN-139, EN-140)
### EN: Eternal Nexus
**TikTok** [source EN-139]
- Caption: Supplement tiktok EN-139.
**FB/IG post** [source EN-139]
- Text: Supplement facebook EN-139.
**X post** [source EN-139]
supplement x EN-139
**TikTok** [source EN-140]
- Caption: Supplement tiktok EN-140.
**FB/IG post** [source EN-140]
- Text: Supplement facebook EN-140.
**X post** [source EN-140]
supplement x EN-140
"""


def _items():
    return parse_copy_bank(BANK)


def _live(*chapters: int):
    allowed = set(chapters)
    return lambda _novel, chapter: chapter in allowed


def test_default_pick_mode_is_bank_day():
    assert WeekdayCadenceConfig().chapter_pick == "bank_day"
    assert WeekdayCadenceConfig().bank_day_start == BANK_DAY_START == date(2026, 11, 23)


def test_date_to_day_mapping_skips_weekends_and_wraps():
    start = date(2026, 11, 23)
    assert bank_day_for(date(2026, 11, 23), start=start, cycle_length=10) == 1
    assert bank_day_for(date(2026, 11, 24), start=start, cycle_length=10) == 2
    assert bank_day_for(date(2026, 11, 27), start=start, cycle_length=10) == 5
    # Saturday and Sunday do not consume a day; Monday 11-30 is day 6.
    assert weekday_offset(start, date(2026, 11, 28)) == weekday_offset(start, date(2026, 11, 27))
    assert weekday_offset(start, date(2026, 11, 29)) == weekday_offset(start, date(2026, 11, 27))
    assert bank_day_for(date(2026, 11, 30), start=start, cycle_length=10) == 6
    # 10 weekdays later wraps to day 1.
    assert bank_day_for(date(2026, 12, 7), start=start, cycle_length=10) == 1
    # Per-novel cycle of 12 (10 + two supplement days): 12-07 is virtual day 11.
    assert bank_day_for(date(2026, 12, 7), start=start, cycle_length=12) == 11
    assert bank_day_for(date(2026, 12, 8), start=start, cycle_length=12) == 12
    assert bank_day_for(date(2026, 12, 9), start=start, cycle_length=12) == 1


def test_supplement_chapters_are_virtual_days_in_file_order():
    items = _items()
    assert supplement_chapters_in_file_order(items, "EN") == [139, 140]
    assert cycle_length_for_novel(items, "EN") == 12
    # Supplement items themselves have no numbered day.
    supp = [item for item in items if item.chapter in {139, 140}]
    assert supp and all(item.bank_day is None and item.weekday is None for item in supp)


def test_recent_live_rule_uses_exact_copy_even_when_bank_day_differs():
    items = _items()
    went = datetime(2026, 11, 21, 20, 45, tzinfo=timezone(timedelta(hours=-7)))
    choice = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),  # bank day 1 would be EN-127
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=went,
        items=items,
        is_live=_live(127, 128, 139, 140),
        start=date(2026, 11, 23),
        numbered_days=10,
    )
    assert choice.pick_rule == RULE_RECENT_LIVE
    assert choice.chapter == 140
    assert choice.copy_source == "copy_bank"
    assert "EN-140" in choice.caption.text
    assert "EN-127" not in choice.caption.text
    assert "EN-139" not in choice.caption.text


def test_recent_live_skipped_when_timestamp_unknown_or_older_than_seven_days():
    items = _items()
    unknown = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=None,
        items=items,
        is_live=_live(127, 140),
        start=date(2026, 11, 23),
    )
    assert unknown.pick_rule == RULE_BANK_DAY
    assert unknown.chapter == 127
    assert is_recent_live(None, date(2026, 11, 23)) is False
    old = datetime(2026, 8, 14, 17, 9)
    assert is_recent_live(old, date(2026, 11, 23), recent_days=7) is False
    skipped = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=old,
        items=items,
        is_live=_live(127, 140),
        start=date(2026, 11, 23),
    )
    assert skipped.pick_rule == RULE_BANK_DAY
    assert skipped.chapter == 127


def test_supplement_virtual_days_before_wrap():
    items = _items()
    # 2026-12-07 is weekday offset 10 -> day 11 of a 12-day EN cycle = first supplement chapter.
    day11 = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 12, 7),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=datetime(2026, 8, 1),  # not recent, so (a) does not fire
        items=items,
        is_live=_live(127, 128, 139, 140),
        start=date(2026, 11, 23),
    )
    assert day11.bank_day == 11
    assert day11.pick_rule == RULE_SUPPLEMENT_DAY
    assert day11.chapter == 139
    assert "EN-139" in day11.caption.text
    day12 = choose_for_platform(
        novel="EN",
        platform="tiktok",
        target=date(2026, 12, 8),
        weekday="Tuesday",
        newest_chapter=140,
        newest_went_live_at=datetime(2026, 8, 1),
        items=items,
        is_live=_live(127, 128, 139, 140),
        start=date(2026, 11, 23),
    )
    assert day12.bank_day == 12
    assert day12.pick_rule == RULE_SUPPLEMENT_DAY
    assert day12.chapter == 140
    assert "EN-140" in day12.caption.text
    wrapped = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 12, 9),
        weekday="Wednesday",
        newest_chapter=140,
        newest_went_live_at=datetime(2026, 8, 1),
        items=items,
        is_live=_live(127, 128, 139, 140),
        start=date(2026, 11, 23),
    )
    assert wrapped.bank_day == 1
    assert wrapped.pick_rule == RULE_BANK_DAY
    assert wrapped.chapter == 127


def test_not_live_bank_day_falls_back_to_newest_exact_or_generated():
    items = _items()
    # Day 1 is EN-127, but 127 is not live; newest 140 has exact copy.
    fallback = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=datetime(2026, 8, 1),
        items=items,
        is_live=_live(140),
        start=date(2026, 11, 23),
    )
    assert fallback.pick_rule == RULE_NEWEST_FALLBACK
    assert fallback.chapter == 140
    assert "EN-140" in fallback.caption.text
    generated = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=200,
        newest_went_live_at=None,
        items=items,
        is_live=_live(200),
        start=date(2026, 11, 23),
    )
    assert generated.pick_rule == RULE_GENERATED
    assert generated.chapter == 200
    assert generated.copy_source == "generated"
    assert generated.caption is None


def test_exact_chapter_match_in_bank_day_selection():
    items = _items()
    choice = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=datetime(2026, 11, 21, 20, 45),
        items=items,
        is_live=_live(127, 139, 140),
        start=date(2026, 11, 23),
    )
    # Recent live 140 must not return the neighboring 139 supplement item.
    assert choice.chapter == 140
    assert "139" not in choice.caption.text
    neighboring = select_bank_caption(
        items, novel="EN", chapter=140, platform="facebook", allowed_chapters=[139, 140]
    )
    assert neighboring is not None
    assert neighboring.chapter == 140
    assert "139" not in neighboring.text


def test_verified_at_never_triggers_recent_live():
    """Confirmation time is not publish time; rule (a) must ignore verified_at."""
    from tools.weekday_cadence import went_live_iso
    from tools.weekday_cadence_overrides import parse_override_entry

    override = parse_override_entry(
        {
            "chapter_id": "EN-140",
            "post_url": "https://www.patreon.com/posts/173664094",
            "verified_at": "2026-11-21T20:45:00-07:00",
            "verified_by": "Product Performance",
            "post_ids": [{"id": "173664094", "tier": "Inner Disciple"}],
        }
    )
    assert override is not None
    assert override.verified_at.startswith("2026-11-21")
    assert override.published_at_values() == []
    assert went_live_iso(None, override) is None

    items = _items()
    # Even if we mistakenly had only verified_at, choose_for_platform gets went_live=None.
    choice = choose_for_platform(
        novel="EN",
        platform="facebook",
        target=date(2026, 11, 23),
        weekday="Monday",
        newest_chapter=140,
        newest_went_live_at=None,
        items=items,
        is_live=_live(127, 140),
        start=date(2026, 11, 23),
    )
    assert choice.pick_rule == RULE_BANK_DAY
    assert choice.chapter == 127
    assert "140" not in choice.caption.text


def test_override_published_at_date_precision_can_trigger_or_skip_rule_a():
    from tools.weekday_cadence import went_live_iso
    from tools.weekday_cadence_bank_days import parse_went_live_at
    from tools.weekday_cadence_overrides import parse_override_entry

    override = parse_override_entry(
        {
            "chapter_id": "HA-99",
            "post_url": "https://www.patreon.com/posts/171234946",
            "verified_at": "2026-11-21T20:45:00-07:00",
            "verified_by": "Product Performance",
            "post_ids": [
                {"id": "171234532", "tier": "Inner Disciple"},
                {
                    "id": "171234946",
                    "tier": "Path Initiate",
                    "published_at": "2026-10-19",
                    "published_at_precision": "date",
                },
            ],
        }
    )
    assert override is not None
    assert override.published_at_values() == ["2026-10-19"]
    iso = went_live_iso(None, override)
    assert iso is not None and iso.startswith("2026-10-19")
    went = parse_went_live_at(iso)
    assert is_recent_live(went, date(2026, 11, 23), recent_days=7) is False

    recent = parse_override_entry(
        {
            "chapter_id": "EN-140",
            "post_url": "https://www.patreon.com/posts/173664094",
            "verified_at": "2026-11-21T20:45:00-07:00",
            "verified_by": "Product Performance",
            "published_at": "2026-11-20",
            "published_at_precision": "date",
        }
    )
    assert recent is not None
    went_recent = parse_went_live_at(went_live_iso(None, recent))
    assert is_recent_live(went_recent, date(2026, 11, 23), recent_days=7) is True

