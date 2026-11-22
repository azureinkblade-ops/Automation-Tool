"""Bank-day rotation for the weekday cadence picker.

Default pick mode maps calendar weekdays onto the bank's numbered days, starting
at Monday 2026-11-23 = day 1, skipping Saturday and Sunday, and wrapping after
the last day of a per-novel cycle.

The cycle length is per novel: 10 numbered bank days plus one virtual day for
each distinct Supplement chapter, in file order. EN therefore has a cycle of
12 (days 11-12 = EN-139, EN-140), HA 16 (HA-94 to HA-99), HP 11 (HP-148), and
SF 11 (SF-126). The Supplement itself has no numbered day; those items are the
virtual days and also the newest-chapter fallback copy.

Priority per novel and platform:
(a) If the novel's newest live chapter went live within the last 7 days
    (ledger or override timestamp; skip if the time is unknown) and has
    exact-match copy, use it.
(b) Otherwise, if the mapped day is 1-10, use that numbered bank item when
    its source chapter is confirmed live.
(c) If the mapped day is 11 or higher, use the corresponding Supplement
    chapter (file order, per novel) when it is confirmed live and has copy.
(d) Fall back to the newest live chapter with exact-match copy, else generated
    copy for that newest chapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Sequence

from tools.weekday_cadence_captions import BankCaption, select_bank_caption
from tools.weekday_cadence_config import (
    CHAPTER_PICK_BANK_DAY,
    CHAPTER_PICK_NEWEST_LIVE,
    NUMBERED_BANK_DAYS,
    RECENT_LIVE_DAYS,
)

RULE_RECENT_LIVE = "recent_live"
RULE_BANK_DAY = "bank_day"
RULE_SUPPLEMENT_DAY = "supplement_day"
RULE_NEWEST_FALLBACK = "newest_live_fallback"
RULE_GENERATED = "generated"

COPY_BANK = "copy_bank"
COPY_GENERATED = "generated"

IsLive = Callable[[str, int], bool]


def weekday_offset(start: date, target: date) -> int:
    """Count Mon-Fri steps from start to target. Start is 0. Weekends add nothing."""
    if target == start:
        return 0
    step = 1 if target > start else -1
    current = start
    offset = 0
    while current != target:
        current += timedelta(days=step)
        if current.weekday() < 5:
            offset += step
    return offset


def bank_day_for(target: date, *, start: date, cycle_length: int) -> int:
    """Map a calendar date to a 1-based day in the cycle (wraps)."""
    length = int(cycle_length) if int(cycle_length) > 0 else 1
    offset = weekday_offset(start, target)
    return (offset % length) + 1


def supplement_chapters_in_file_order(items: Sequence[BankCaption], novel: str) -> list[int]:
    """Distinct Supplement chapters for a novel, in the order they appear in the bank."""
    abbr = str(novel).strip().upper()
    seen: list[int] = []
    for item in items:
        if item.novel != abbr or item.bank_day is not None:
            continue
        if item.chapter not in seen:
            seen.append(item.chapter)
    return seen


def cycle_length_for_novel(
    items: Sequence[BankCaption],
    novel: str,
    *,
    numbered_days: int = NUMBERED_BANK_DAYS,
) -> int:
    return int(numbered_days) + len(supplement_chapters_in_file_order(items, novel))


def parse_went_live_at(value: object, *, default_tz: timezone | None = None) -> datetime | None:
    """Parse a ledger or override timestamp. Returns None if missing or unusable."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        current = value
    else:
        text = str(value).strip()
        if not text:
            return None
        current = None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                current = datetime.fromisoformat(candidate)
                break
            except ValueError:
                current = None
        if current is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    current = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if current is None:
            return None
    if current.tzinfo is None and default_tz is not None:
        current = current.replace(tzinfo=default_tz)
    return current


def earliest_went_live_at(values: Iterable[object], *, default_tz: timezone | None = None) -> datetime | None:
    parsed = [stamp for stamp in (parse_went_live_at(value, default_tz=default_tz) for value in values) if stamp is not None]
    if not parsed:
        return None
    aware = [stamp for stamp in parsed if stamp.tzinfo is not None]
    naive = [stamp for stamp in parsed if stamp.tzinfo is None]
    if aware and naive:
        if default_tz is not None:
            naive = [stamp.replace(tzinfo=default_tz) for stamp in naive]
            aware = aware + naive
        else:
            aware = [stamp.replace(tzinfo=None) for stamp in aware] + naive
        return min(aware)
    return min(parsed)


def is_recent_live(went_live_at: datetime | None, target: date, *, recent_days: int = RECENT_LIVE_DAYS) -> bool:
    """True when a known went-live time is within recent_days of the target date.

    If the timestamp is unknown, this rule is skipped (returns False).
    """
    if went_live_at is None:
        return False
    live_date = went_live_at.date()
    return (target - live_date).days <= int(recent_days) and (live_date - target).days <= int(recent_days)


@dataclass(frozen=True)
class BankDayChoice:
    chapter: int
    pick_rule: str
    copy_source: str
    bank_day: int
    cycle_length: int
    caption: BankCaption | None = None


def _exact(
    items: Sequence[BankCaption],
    *,
    novel: str,
    chapter: int,
    platform: str,
    weekday: str | None,
    bank_day: int | None = None,
) -> BankCaption | None:
    return select_bank_caption(
        items,
        novel=novel,
        chapter=chapter,
        platform=platform,
        weekday=weekday,
        allowed_chapters=[chapter],
        bank_day=bank_day,
    )


def choose_for_platform(
    *,
    novel: str,
    platform: str,
    target: date,
    weekday: str | None,
    newest_chapter: int,
    newest_went_live_at: datetime | None,
    items: Sequence[BankCaption],
    is_live: IsLive,
    start: date,
    numbered_days: int = NUMBERED_BANK_DAYS,
    recent_days: int = RECENT_LIVE_DAYS,
    pick_mode: str = CHAPTER_PICK_BANK_DAY,
) -> BankDayChoice:
    """Apply (a)-(d) or the newest-live option. Never invents a chapter."""
    cycle = cycle_length_for_novel(items, novel, numbered_days=numbered_days)
    mapped = bank_day_for(target, start=start, cycle_length=cycle)

    if str(pick_mode) == CHAPTER_PICK_NEWEST_LIVE:
        copy = _exact(items, novel=novel, chapter=newest_chapter, platform=platform, weekday=weekday)
        return BankDayChoice(
            chapter=newest_chapter,
            pick_rule=RULE_NEWEST_FALLBACK if copy is not None else RULE_GENERATED,
            copy_source=COPY_BANK if copy is not None else COPY_GENERATED,
            bank_day=mapped,
            cycle_length=cycle,
            caption=copy,
        )

    # (a) recent newest live chapter with exact-match copy
    if is_recent_live(newest_went_live_at, target, recent_days=recent_days):
        copy = _exact(items, novel=novel, chapter=newest_chapter, platform=platform, weekday=weekday)
        if copy is not None:
            return BankDayChoice(
                chapter=newest_chapter,
                pick_rule=RULE_RECENT_LIVE,
                copy_source=COPY_BANK,
                bank_day=mapped,
                cycle_length=cycle,
                caption=copy,
            )

    # (b) numbered bank day 1-10
    if 1 <= mapped <= int(numbered_days):
        day_items = [
            item
            for item in items
            if item.novel == str(novel).strip().upper()
            and item.bank_day == mapped
            and platform in item.platforms
        ]
        if weekday:
            named = [item for item in day_items if item.weekday == weekday]
            if named:
                day_items = named
        if day_items:
            chosen = day_items[0]
            if is_live(chosen.novel, chosen.chapter):
                copy = _exact(
                    items,
                    novel=novel,
                    chapter=chosen.chapter,
                    platform=platform,
                    weekday=weekday,
                    bank_day=mapped,
                )
                if copy is not None:
                    return BankDayChoice(
                        chapter=chosen.chapter,
                        pick_rule=RULE_BANK_DAY,
                        copy_source=COPY_BANK,
                        bank_day=mapped,
                        cycle_length=cycle,
                        caption=copy,
                    )

    # (c) virtual supplement days 11+
    if mapped > int(numbered_days):
        supplements = supplement_chapters_in_file_order(items, novel)
        index = mapped - int(numbered_days) - 1
        if 0 <= index < len(supplements):
            chapter = supplements[index]
            if is_live(str(novel).strip().upper(), chapter):
                copy = _exact(items, novel=novel, chapter=chapter, platform=platform, weekday=weekday)
                if copy is not None:
                    return BankDayChoice(
                        chapter=chapter,
                        pick_rule=RULE_SUPPLEMENT_DAY,
                        copy_source=COPY_BANK,
                        bank_day=mapped,
                        cycle_length=cycle,
                        caption=copy,
                    )

    # (d) newest live exact-match copy, else generated
    copy = _exact(items, novel=novel, chapter=newest_chapter, platform=platform, weekday=weekday)
    return BankDayChoice(
        chapter=newest_chapter,
        pick_rule=RULE_NEWEST_FALLBACK if copy is not None else RULE_GENERATED,
        copy_source=COPY_BANK if copy is not None else COPY_GENERATED,
        bank_day=mapped,
        cycle_length=cycle,
        caption=copy,
    )
