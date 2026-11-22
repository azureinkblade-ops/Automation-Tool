"""Weekday cadence planner: chapter pick, identity cutoff, and item assembly.

Chapter pick defaults to each novel's newest chapter verified live on Patreon
from local chapter_ledger records (postedToPatreon plus post records / tier
posted flags). Royal Road is a config option (postedToRoyalRoad or
royalRoadExists). release_status.patreonExists is still honored when present
in a provided records payload, but the default loader no longer reads that
table because it stopped receiving EN posted flags after EN-132.
Missing or unverifiable records hold that novel's items instead of guessing.
This module never calls Patreon, Royal Road, or social APIs, and it never
writes to the ledger or release_status tables.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
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
    if name in {"America/Phoenix", "US/Arizona"}:
        return timezone(timedelta(hours=-7))
    raise RuntimeError(f"unknown timezone {name!r} and tzdata is unavailable")


from tools.weekday_cadence_config import (
    CHAPTER_PICK_BANK_DAY,
    CHAPTER_SOURCE_PATREON,
    CHAPTER_SOURCE_ROYAL_ROAD,
    DEPICTION_GOVERNED,
    DEPICTION_NOT_GOVERNED,
    DEPICTION_UNKNOWN,
    HOLD_AWAITING_DAVID,
    HOLD_IDENTITY_AWAITING,
    HOLD_IDENTITY_UNAPPROVED,
    HOLD_NO_DEPICTION_EVIDENCE,
    HOLD_UNVERIFIED_SOURCE,
    KNOWN_PATREON_TIERS,
    STATUS_AWAITING_APPROVAL,
    STATUS_AWAITING_DAVID,
    STATUS_HELD,
    STATUS_READY,
    STATIC_PLATFORMS,
    TIER_INNER,
    TIER_PATH,
    VIDEO_PLATFORMS,
    WEEKDAYS,
    WeekdayCadenceConfig,
)
from tools.weekday_cadence_bank_days import choose_for_platform, earliest_went_live_at
from tools.weekday_cadence_manifest import CadenceItem, item_id
from tools.weekday_cadence_overrides import (
    PatreonLiveOverride,
    load_patreon_live_overrides,
    override_for_chapter,
    overrides_for_novel,
)

EXISTS_FLAG = {
    CHAPTER_SOURCE_PATREON: "patreonExists",
    CHAPTER_SOURCE_ROYAL_ROAD: "royalRoadExists",
}

PATREON_POST_ID_KEYS = (
    "patreonInnerDisciplePostId",
    "innerDisciplePostId",
    "patreonPathInitiatePostId",
    "pathInitiatePostId",
    "patreonPostId",
    "postId",
)


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or str(value).strip().lower() == "true"


@dataclass(frozen=True)
class ChapterPick:
    novel: str
    source_platform: str
    chapter: int | None
    verified: bool
    hold_reason: str | None = None
    live_tiers: tuple[str, ...] = ()
    went_live_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel": self.novel,
            "source_platform": self.source_platform,
            "source_chapter": self.chapter,
            "verified": self.verified,
            "hold_reason": self.hold_reason,
            "live_tiers": list(self.live_tiers),
            "went_live_at": self.went_live_at,
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


def patreon_post_ids(entry: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for key in PATREON_POST_ID_KEYS:
        value = str(entry.get(key) or "").strip()
        if value and value not in found:
            found.append(value)
    extra = entry.get("patreon_post_records") or entry.get("post_records") or []
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping):
                value = str(row.get("post_id") or row.get("id") or row.get("live_url") or "").strip()
            else:
                value = str(row or "").strip()
            if value and value not in found:
                found.append(value)
    return found


def has_patreon_post_evidence(entry: Mapping[str, Any]) -> bool:
    """True when the ledger row has post IDs or explicit tier-posted flags.

    Schedule dates alone (innerDiscipleDate / pathInitiateDate) are not evidence.
    """
    if patreon_post_ids(entry):
        return True
    if _truthy(entry.get("patreonInnerDisciplePosted")) or _truthy(entry.get("patreonPathInitiatePosted")):
        return True
    return False


def is_verified_live(entry: Mapping[str, Any], source: str) -> bool:
    """True only with explicit live evidence. No schedule-date inference."""
    platform = str(source).strip().lower()
    if platform == CHAPTER_SOURCE_PATREON:
        if _truthy(entry.get("patreonExists")):
            return True
        # chapter_ledger: postedToPatreon plus post IDs or tier posted flags.
        return _truthy(entry.get("postedToPatreon")) and has_patreon_post_evidence(entry)
    if platform == CHAPTER_SOURCE_ROYAL_ROAD:
        if _truthy(entry.get("royalRoadExists")):
            return True
        if _truthy(entry.get("postedToRoyalRoad")):
            url = str(entry.get("royalRoadUrl") or entry.get("royalRoadChapterUrl") or "").strip()
            return bool(url) or _truthy(entry.get("royalRoadExists"))
        return False
    return False


def live_tiers_from_entry(entry: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(entry, Mapping):
        return []
    declared = entry.get("tiers_live") or entry.get("live_tiers") or []
    names: list[str] = []
    if isinstance(declared, (list, tuple)):
        for item in declared:
            name = str(item or "").strip()
            if name and name not in names:
                names.append(name)
    inner_id = str(entry.get("patreonInnerDisciplePostId") or entry.get("innerDisciplePostId") or "").strip()
    path_id = str(entry.get("patreonPathInitiatePostId") or entry.get("pathInitiatePostId") or "").strip()
    if _truthy(entry.get("patreonInnerDisciplePosted")) or inner_id:
        if TIER_INNER not in names:
            names.append(TIER_INNER)
    if _truthy(entry.get("patreonPathInitiatePosted")) or path_id:
        if TIER_PATH not in names:
            names.append(TIER_PATH)
    return _order_tiers(names)


def live_tiers_from_override(override: PatreonLiveOverride | None) -> list[str]:
    if override is None:
        return []
    names = [str(item).strip() for item in (override.tiers_live or ()) if str(item).strip()]
    for ref in override.post_ids:
        if ref.tier and ref.tier not in names:
            names.append(ref.tier)
    return _order_tiers(names)


def _order_tiers(names: Sequence[str]) -> list[str]:
    known = [tier for tier in KNOWN_PATREON_TIERS if tier in names]
    extra = [name for name in names if name not in known]
    return known + extra


def resolve_live_tiers(
    *,
    entry: Mapping[str, Any] | None,
    override: PatreonLiveOverride | None,
) -> tuple[str, ...]:
    # A confirmed override is the authority for that chapter's live tiers.
    from_override = live_tiers_from_override(override)
    if from_override:
        return tuple(from_override)
    return tuple(live_tiers_from_entry(entry))




WENT_LIVE_KEYS = (
    "patreonPostedAt",
    "patreonInnerDisciplePostedAt",
    "patreonPathInitiatePostedAt",
)


def went_live_iso(entry: Mapping[str, Any] | None, override, default_tz=None) -> str | None:
    values = []
    if isinstance(entry, Mapping):
        values.extend(entry.get(key) for key in WENT_LIVE_KEYS)
    if override is not None and hasattr(override, "published_at_values"):
        values.extend(override.published_at_values())
    elif override is not None and hasattr(override, "publish_live_at_values"):
        values.extend(override.publish_live_at_values())
    stamp = earliest_went_live_at(values, default_tz=default_tz)
    if stamp is None:
        return None
    return stamp.isoformat()


def chapter_entry_map(records: Mapping[str, Any] | None, novel: str) -> dict[int, dict[str, Any]]:
    abbr = str(novel).strip().upper()
    return {
        chapter: entry
        for entry_abbr, chapter, entry in iter_release_entries(records)
        if entry_abbr == abbr
    }


def is_chapter_live(
    novel: str,
    chapter: int,
    records: Mapping[str, Any] | None,
    *,
    source: str,
    overrides=None,
) -> bool:
    from tools.weekday_cadence_overrides import override_for_chapter

    if str(source).strip().lower() == CHAPTER_SOURCE_PATREON:
        if override_for_chapter(overrides or [], novel, chapter) is not None:
            return True
    entry = chapter_entry_map(records, novel).get(int(chapter))
    return bool(entry) and is_verified_live(entry, source)


def live_tiers_for_chapter(
    novel: str,
    chapter: int,
    records: Mapping[str, Any] | None,
    *,
    overrides=None,
):
    from tools.weekday_cadence_overrides import override_for_chapter

    entry = chapter_entry_map(records, novel).get(int(chapter))
    override = override_for_chapter(overrides or [], novel, chapter)
    return resolve_live_tiers(entry=entry, override=override)


def newest_verified_chapter(
    novel: str,
    records: Mapping[str, Any] | None,
    *,
    source: str,
    overrides: Sequence[PatreonLiveOverride] | None = None,
) -> ChapterPick:
    abbr = str(novel).strip().upper()
    platform = str(source).strip().lower()
    ledger_entries = {
        chapter: entry
        for entry_abbr, chapter, entry in iter_release_entries(records)
        if entry_abbr == abbr
    }
    ledger_numbers = [
        chapter
        for chapter, entry in ledger_entries.items()
        if is_verified_live(entry, platform)
    ]
    override_numbers: list[int] = []
    override_list = list(overrides or [])
    if platform == CHAPTER_SOURCE_PATREON:
        override_numbers = [entry.chapter for entry in overrides_for_novel(override_list, abbr)]
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
    chapter = max(verified_numbers)
    override = override_for_chapter(override_list, abbr, chapter) if platform == CHAPTER_SOURCE_PATREON else None
    return ChapterPick(
        novel=abbr,
        source_platform=platform,
        chapter=chapter,
        verified=True,
        hold_reason=None,
        live_tiers=resolve_live_tiers(entry=ledger_entries.get(chapter), override=override),
        went_live_at=went_live_iso(ledger_entries.get(chapter), override),
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


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_live_chapter_records(root: Path) -> dict[str, Any] | None:
    """Read chapter_ledger (and any matching Patreon post_records) read-only.

    Never calls init_db, never writes, and never uses release_status.
    """
    db_path = Path(root) / "automation_state.db"
    if not db_path.is_file():
        return None
    try:
        conn = _sqlite_readonly(db_path)
    except Exception:
        return None
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute("SELECT ledger_key, abbr, chapter, payload_json FROM chapter_ledger").fetchall()
        except sqlite3.Error:
            return None
        post_rows = []
        try:
            post_rows = conn.execute(
                """
                SELECT novel, chapter, live_url, payload_json, automation_record_id
                FROM post_records
                WHERE lower(platform) = 'patreon'
                """
            ).fetchall()
        except sqlite3.Error:
            post_rows = []
    finally:
        conn.close()

    extras: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in post_rows:
        abbr = str(row["novel"] or "").strip().upper()
        try:
            chapter = int(row["chapter"])
        except (TypeError, ValueError):
            continue
        if not abbr or chapter <= 0:
            continue
        extras.setdefault((abbr, chapter), []).append(
            {
                "id": str(row["automation_record_id"] or ""),
                "live_url": str(row["live_url"] or ""),
            }
        )

    chapters: dict[str, Any] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            continue
        abbr = str(row["abbr"] or payload.get("abbr") or "").strip().upper()
        try:
            chapter = int(row["chapter"] if row["chapter"] not in (None, "") else payload.get("chapter"))
        except (TypeError, ValueError):
            continue
        if not abbr or chapter <= 0:
            continue
        key = str(row["ledger_key"] or f"{abbr}-{chapter}")
        entry = dict(payload)
        entry.setdefault("abbr", abbr)
        entry.setdefault("chapter", chapter)
        if extras.get((abbr, chapter)):
            entry.setdefault("patreon_post_records", extras[(abbr, chapter)])
        chapters[key] = entry
    if not chapters:
        return None
    return {"schemaVersion": 1, "chapters": chapters, "source": "chapter_ledger"}


def load_release_status_records(root: Path) -> dict[str, Any] | None:
    """Legacy loader kept for comparison tests. Default cadence pick does not use it."""
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
        item.hold_reason = HOLD_IDENTITY_AWAITING
        return item
    item.status = STATUS_HELD
    item.hold_reason = HOLD_IDENTITY_UNAPPROVED
    return item


def apply_x_default(item: CadenceItem, config: WeekdayCadenceConfig) -> CadenceItem:
    """X is text-only: no media stage, no identity check, awaiting David to post."""
    if item.platform != "x":
        return item
    if item.status == STATUS_HELD and item.hold_reason:
        return item
    item.status = config.x_status or STATUS_AWAITING_DAVID
    if not item.hold_reason:
        item.hold_reason = HOLD_AWAITING_DAVID
    return item


def merge_depiction(*values: str | None) -> str:
    cleaned = [str(value or "").strip() or DEPICTION_UNKNOWN for value in values]
    if DEPICTION_GOVERNED in cleaned:
        return DEPICTION_GOVERNED
    if DEPICTION_NOT_GOVERNED in cleaned:
        return DEPICTION_NOT_GOVERNED
    return DEPICTION_UNKNOWN


def apply_depiction_gate(
    item: CadenceItem,
    *,
    approved: bool,
    now: datetime,
    deadline: datetime,
    pipeline_depiction: str | None = None,
) -> CadenceItem:
    """Per-item identity gate. Never uses novel membership. Never applies to X."""
    if item.platform == "x":
        return item
    if item.status == STATUS_HELD and item.hold_reason:
        return item
    evidence = merge_depiction(getattr(item, "depiction", None), pipeline_depiction)
    item.depiction = evidence
    if evidence == DEPICTION_NOT_GOVERNED:
        return item
    if evidence == DEPICTION_GOVERNED:
        return apply_identity_cutoff(
            item,
            needs_approval=True,
            approved=approved,
            now=now,
            deadline=deadline,
        )
    item.status = STATUS_AWAITING_APPROVAL
    item.hold_reason = HOLD_NO_DEPICTION_EVIDENCE
    return item


def ensure_hold_reasons(items: list[CadenceItem]) -> list[CadenceItem]:
    """Every non-ready item must have a hold reason, never an empty one."""
    for item in items:
        if item.status == STATUS_READY:
            continue
        if not str(item.hold_reason or "").strip():
            item.hold_reason = f"MISSING_HOLD_REASON:{item.status}"
    return items


def apply_unverified_hold(item: CadenceItem, pick: ChapterPick) -> CadenceItem:
    if pick.verified and pick.chapter is not None:
        item.source_chapter = pick.chapter
        item.source_platform = pick.source_platform
        item.live_tiers = list(pick.live_tiers)
        return item
    item.source_chapter = None
    item.source_platform = pick.source_platform
    item.live_tiers = []
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
            live_tiers=list(pick.live_tiers),
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
    bank=None,
    target: date | None = None,
    weekday: str | None = None,
    default_tz=None,
) -> tuple[list[CadenceItem], dict[str, ChapterPick]]:
    picks = pick_chapters(records, config, overrides=overrides)
    # Recompute went_live with timezone when provided.
    if default_tz is not None:
        adjusted = {}
        from tools.weekday_cadence_overrides import override_for_chapter

        for novel, pick in picks.items():
            if not pick.verified or pick.chapter is None:
                adjusted[novel] = pick
                continue
            entry = chapter_entry_map(records, novel).get(pick.chapter)
            override = (
                override_for_chapter(overrides or [], novel, pick.chapter)
                if pick.source_platform == CHAPTER_SOURCE_PATREON
                else None
            )
            adjusted[novel] = ChapterPick(
                novel=pick.novel,
                source_platform=pick.source_platform,
                chapter=pick.chapter,
                verified=pick.verified,
                hold_reason=pick.hold_reason,
                live_tiers=pick.live_tiers,
                went_live_at=went_live_iso(entry, override, default_tz=default_tz),
            )
        picks = adjusted
    items: list[CadenceItem] = []
    for novel, pick in picks.items():
        caps = (captions_by_novel or {}).get(novel) if captions_by_novel else None
        if bank is None or target is None or not pick.verified or pick.chapter is None:
            items.extend(plan_items_for_novel(pick, config, captions=caps))
            continue
        from tools.weekday_cadence_bank_days import parse_went_live_at

        went_live = parse_went_live_at(pick.went_live_at, default_tz=default_tz)
        for platform in (*STATIC_PLATFORMS, *VIDEO_PLATFORMS):
            choice = choose_for_platform(
                novel=novel,
                platform=platform,
                target=target,
                weekday=weekday,
                newest_chapter=pick.chapter,
                newest_went_live_at=went_live,
                items=list(bank or []),
                is_live=lambda abbr, chapter, _records=records, _src=config.chapter_source, _ov=overrides: is_chapter_live(
                    abbr, chapter, _records, source=_src, overrides=_ov
                ),
                start=config.bank_day_start,
                numbered_days=config.numbered_bank_days,
                recent_days=config.recent_live_days,
                pick_mode=config.chapter_pick,
            )
            item = CadenceItem(
                id=item_id(pick.novel, platform),
                platform=platform,
                novel=pick.novel,
                source_chapter=choice.chapter,
                source_platform=pick.source_platform,
                caption=str((caps or {}).get(platform) or ""),
                status=STATUS_READY,
                hold_reason=None,
                live_tiers=list(live_tiers_for_chapter(novel, choice.chapter, records, overrides=overrides)),
                pick_mode=config.chapter_pick,
                bank_day=choice.bank_day,
                pick_rule=choice.pick_rule,
                copy_source=choice.copy_source,
                depiction=(
                    choice.caption.depiction
                    if choice.caption is not None
                    else DEPICTION_UNKNOWN
                ),
            )
            item = apply_unverified_hold(item, pick)
            # restore the chosen chapter after unverified hold (pick is newest; still verified)
            if pick.verified and pick.chapter is not None:
                item.source_chapter = choice.chapter
                item.live_tiers = list(live_tiers_for_chapter(novel, choice.chapter, records, overrides=overrides))
            item = apply_x_default(item, config)
            items.append(item)
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
