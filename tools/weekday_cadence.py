"""Weekday cadence planner: chapter pick, identity cutoff, and item assembly.

Chapter pick defaults to each novel's newest chapter with verified live Patreon
status in local release-status records (patreonExists). Royal Road is a config
option (royalRoadExists). Missing or unverifiable records hold that novel's items
instead of guessing. This module never calls Patreon, Royal Road, or social APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def timezone_for(name: str):
    """America/Phoenix is UTC-7 year-round. Fall back if tzdata is missing."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    if name in {'America/Phoenix', 'US/Arizona'}:
        return timezone(timedelta(hours=-7))
    raise RuntimeError(f'unknown timezone {name!r} and tzdata is unavailable')

from tools.weekday_cadence_config import (
    CHAPTER_SOURCE_PATREON,
    CHAPTER_SOURCE_ROYAL_ROAD,
    HOLD_IDENTITY_UNAPPROVED,
    HOLD_UNVERIFIED_SOURCE,
    STATUS_AWAITING_APPROVAL,
    STATUS_AWAITING_DAVID,
    STATUS_HELD,
    STATUS_READY,
    STATIC_PLATFORMS,
    VIDEO_PLATFORMS,
    WEEKDAYS,
    WeekdayCadenceConfig,
)
from tools.weekday_cadence_manifest import CadenceItem, item_id
from tools.weekday_cadence_overrides import (
    PatreonLiveOverride,
    load_patreon_live_overrides,
    overrides_for_novel,
)

EXISTS_FLAG = {
    CHAPTER_SOURCE_PATREON: "patreonExists",
    CHAPTER_SOURCE_ROYAL_ROAD: "royalRoadExists",
}


@dataclass(frozen=True)
class ChapterPick:
    novel: str
    source_platform: str
    chapter: int | None
    verified: bool
    hold_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel": self.novel,
            "source_platform": self.source_platform,
            "source_chapter": self.chapter,
            "verified": self.verified,
            "hold_reason": self.hold_reason,
        }


def parse_iso_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def weekday_name(value: date) -> str:
    return value.strftime("%A")


def is_weekday(value: date) -> bool:
    return weekday_name(value) in WEEKDAYS


def next_weekday(today: date | str) -> date:
    """The next Mon-Fri date after ``today`` (never today). Sat/Sun -> Monday."""
    current = parse_iso_date(today)
    candidate = current + timedelta(days=1)
    while not is_weekday(candidate):
        candidate += timedelta(days=1)
    return candidate


def approval_deadline_for(target: date | str, config: WeekdayCadenceConfig) -> datetime:
    day = parse_iso_date(target) - timedelta(days=1)
    tz = timezone_for(config.timezone)
    return datetime.combine(day, time(hour=int(config.identity_approval_hour), minute=0), tzinfo=tz)


def now_now(config: WeekdayCadenceConfig, now: datetime | None = None) -> datetime:
    tz = timezone_for(config.timezone)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _parse_record_key(key: Any, entry: Mapping[str, Any]) -> tuple[str, int] | None:
    abbr = str(entry.get("abbr") or "").strip().upper()
    chapter = entry.get("chapter")
    if abbr and chapter not in (None, ""):
        try:
            return abbr, int(chapter)
        except (TypeError, ValueError):
            return None
    text = str(key or "").strip().upper().replace("_", "-")
    if "-" not in text:
        return None
    left, right = text.rsplit("-", 1)
    if not left or not right.lstrip("-").isdigit():
        return None
    try:
        return left, int(right)
    except (TypeError, ValueError):
        return None


def iter_release_entries(records: Mapping[str, Any] | None) -> list[tuple[str, int, dict[str, Any]]]:
    if not isinstance(records, Mapping):
        return []
    chapters = records.get("chapters")
    if not isinstance(chapters, Mapping):
        return []
    out: list[tuple[str, int, dict[str, Any]]] = []
    for key, entry in chapters.items():
        if not isinstance(entry, Mapping):
            continue
        parsed = _parse_record_key(key, entry)
        if parsed is None:
            continue
        abbr, chapter = parsed
        if chapter <= 0:
            continue
        out.append((abbr, chapter, dict(entry)))
    return out


def is_verified_live(entry: Mapping[str, Any], source: str) -> bool:
    """True only when the record explicitly marks the chapter live. No schedule inference."""
    flag = EXISTS_FLAG.get(str(source).strip().lower())
    if not flag:
        return False
    value = entry.get(flag)
    return value is True or value == 1 or str(value).strip().lower() == "true"


def newest_verified_chapter(
    novel: str,
    records: Mapping[str, Any] | None,
    *,
    source: str,
    overrides: Sequence[PatreonLiveOverride] | None = None,
) -> ChapterPick:
    abbr = str(novel).strip().upper()
    platform = str(source).strip().lower()
    ledger_numbers = [
        chapter
        for entry_abbr, chapter, entry in iter_release_entries(records)
        if entry_abbr == abbr and is_verified_live(entry, platform)
    ]
    override_numbers: list[int] = []
    if platform == CHAPTER_SOURCE_PATREON:
        override_numbers = [entry.chapter for entry in overrides_for_novel(overrides or [], abbr)]
    # An override beats the ledger's not-posted flag; without one, the ledger stays the source.
    verified_numbers = set(ledger_numbers) | set(override_numbers)
    if not verified_numbers:
        return ChapterPick(
            novel=abbr,
            source_platform=platform,
            chapter=None,
            verified=False,
            hold_reason=f"{HOLD_UNVERIFIED_SOURCE}:{platform}",
        )
    return ChapterPick(
        novel=abbr,
        source_platform=platform,
        chapter=max(verified_numbers),
        verified=True,
        hold_reason=None,
    )


def pick_chapters(
    records: Mapping[str, Any] | None,
    config: WeekdayCadenceConfig,
    *,
    overrides: Sequence[PatreonLiveOverride] | None = None,
) -> dict[str, ChapterPick]:
    return {
        novel: newest_verified_chapter(
            novel, records, source=config.chapter_source, overrides=overrides
        )
        for novel in config.novels
    }


def load_release_status_records(root: Path) -> dict[str, Any] | None:
    """Read local release-status records only. Never calls a network API."""
    try:
        import automation_db
    except Exception:
        return None
    try:
        payload = automation_db.load_release_status(Path(root))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def apply_identity_cutoff(
    item: CadenceItem,
    *,
    needs_approval: bool,
    approved: bool,
    now: datetime,
    deadline: datetime,
) -> CadenceItem:
    if not needs_approval or approved:
        return item
    if now <= deadline:
        item.status = STATUS_AWAITING_APPROVAL
        item.hold_reason = None
        return item
    item.status = STATUS_HELD
    item.hold_reason = HOLD_IDENTITY_UNAPPROVED
    return item


def apply_x_default(item: CadenceItem, config: WeekdayCadenceConfig) -> CadenceItem:
    if item.platform != "x":
        return item
    if item.status == STATUS_HELD or item.status == STATUS_AWAITING_APPROVAL:
        return item
    item.status = config.x_status or STATUS_AWAITING_DAVID
    return item


def apply_unverified_hold(item: CadenceItem, pick: ChapterPick) -> CadenceItem:
    if pick.verified and pick.chapter is not None:
        item.source_chapter = pick.chapter
        item.source_platform = pick.source_platform
        return item
    item.source_chapter = None
    item.source_platform = pick.source_platform
    item.status = STATUS_HELD
    item.hold_reason = pick.hold_reason or f"{HOLD_UNVERIFIED_SOURCE}:{pick.source_platform}"
    item.media = []
    return item


def plan_items_for_novel(
    pick: ChapterPick,
    config: WeekdayCadenceConfig,
    *,
    captions: Mapping[str, str] | None = None,
) -> list[CadenceItem]:
    copy = captions or {}
    items: list[CadenceItem] = []
    for platform in (*STATIC_PLATFORMS, *VIDEO_PLATFORMS):
        item = CadenceItem(
            id=item_id(pick.novel, platform),
            platform=platform,
            novel=pick.novel,
            source_chapter=pick.chapter,
            source_platform=pick.source_platform,
            caption=str(copy.get(platform) or ""),
            status=STATUS_READY if pick.verified else STATUS_HELD,
            hold_reason=None if pick.verified else (pick.hold_reason or f"{HOLD_UNVERIFIED_SOURCE}:{pick.source_platform}"),
        )
        item = apply_unverified_hold(item, pick)
        item = apply_x_default(item, config)
        items.append(item)
    return items


def plan_day_items(
    records: Mapping[str, Any] | None,
    config: WeekdayCadenceConfig,
    *,
    captions_by_novel: Mapping[str, Mapping[str, str]] | None = None,
    overrides: Sequence[PatreonLiveOverride] | None = None,
) -> tuple[list[CadenceItem], dict[str, ChapterPick]]:
    picks = pick_chapters(records, config, overrides=overrides)
    items: list[CadenceItem] = []
    for novel, pick in picks.items():
        caps = (captions_by_novel or {}).get(novel) if captions_by_novel else None
        items.extend(plan_items_for_novel(pick, config, captions=caps))
    return items, picks


def approval_inbox_entries(
    items: Sequence[CadenceItem],
    *,
    approval_deadline: str,
) -> list[dict[str, Any]]:
    """Shape compatible with approval-inbox aggregators. Relative fields only."""
    entries: list[dict[str, Any]] = []
    for item in items:
        if item.status != STATUS_AWAITING_APPROVAL:
            continue
        entries.append(
            {
                "kind": "identity_cadence_batch",
                "abbr": item.novel,
                "chapter": item.source_chapter,
                "platform": item.platform,
                "id": item.id,
                "dueBy": approval_deadline,
                "status": item.status,
                "media": list(item.media),
            }
        )
    return entries


RecordsLoader = Callable[[Path], dict[str, Any] | None]
