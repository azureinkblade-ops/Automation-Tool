from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


VALID_NOVELS = {"EN", "HA", "SF", "HP"}
VALID_STATUSES = {
    "planned",
    "draft_prepared",
    "review_needed",
    "posted",
    "skipped_exists",
    "needs_repair",
    "blocked",
}


@dataclass(frozen=True)
class ReleasePlanRequest:
    novel: str
    release_through_chapter: int
    first_inner_disciple_date: date
    weekday_only: bool = True
    start_chapter: int | None = None
    notes: str = ""
    dry_run: bool = False
    targets: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReleasePlanRequest":
        novel = normalize_novel(payload.get("novel") or payload.get("abbr") or "ALL", allow_all=True)
        through = int_value(payload.get("releaseThroughChapter") or payload.get("throughChapter") or payload.get("chapter") or 0)
        first_date = parse_date(payload.get("firstInnerDiscipleDate") or payload.get("innerDiscipleDate") or payload.get("startDate"))
        start = int_value(payload.get("startChapter") or 0) or None
        targets = {}
        raw_targets = payload.get("targets")
        if isinstance(raw_targets, dict):
            for raw_abbr, raw_chapter in raw_targets.items():
                abbr = normalize_novel(raw_abbr, allow_all=False)
                chapter = int_value(raw_chapter)
                if abbr and chapter > 0:
                    targets[abbr] = chapter
        if through <= 0 and targets:
            through = max(targets.values())
        if through <= 0:
            raise ValueError("Release through chapter is required.")
        if not first_date:
            raise ValueError("First Inner Disciple date is required.")
        return cls(
            novel=novel,
            release_through_chapter=through,
            first_inner_disciple_date=first_date,
            weekday_only=bool(payload.get("weekdayOnly", True)),
            start_chapter=start,
            notes=str(payload.get("notes") or "").strip(),
            dry_run=bool(payload.get("dryRun", False)),
            targets=targets,
        )


@dataclass(frozen=True)
class ReleasePlanRow:
    release_plan_id: str
    novel_id: str
    novel_abbr: str
    novel: str
    chapter_number: int
    chapter_title: str
    chapter_source_path: str
    inner_disciple_date: str
    path_initiate_date: str
    royal_road_date: str
    patreon_inner_status: str = "planned"
    patreon_path_status: str = "planned"
    royal_road_status: str = "planned"
    last_prepared_at: str = ""
    last_error: str = ""
    notes: str = ""

    @property
    def key(self) -> str:
        return f"{self.novel_abbr}-{self.chapter_number}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "releasePlanId": self.release_plan_id,
            "key": self.key,
            "novelId": self.novel_id,
            "novelAbbr": self.novel_abbr,
            "abbr": self.novel_abbr,
            "novel": self.novel,
            "chapterNumber": self.chapter_number,
            "chapter": self.chapter_number,
            "chapterTitle": self.chapter_title,
            "title": self.chapter_title,
            "chapterSourcePath": self.chapter_source_path,
            "innerDiscipleDate": self.inner_disciple_date,
            "pathInitiateDate": self.path_initiate_date,
            "royalRoadDate": self.royal_road_date,
            "patreonInnerStatus": self.patreon_inner_status,
            "patreonPathStatus": self.patreon_path_status,
            "royalRoadStatus": self.royal_road_status,
            "lastPreparedAt": self.last_prepared_at,
            "lastError": self.last_error,
            "notes": self.notes,
        }


def normalize_novel(value: Any, *, allow_all: bool = True) -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "ETERNAL_NEXUS": "EN",
        "HEAVENLY_ASCENSION_SYSTEM": "HA",
        "SOULFORGE": "SF",
        "SOUL_FORGE": "SF",
        "SOUL_FORGE_ERA": "SF",
        "HUNDREDFOLD_PATH": "HP",
        "THE_HUNDREDFOLD_PATH": "HP",
    }
    if allow_all and text in {"", "ALL", "*"}:
        return "ALL"
    if text in VALID_NOVELS:
        return text
    return aliases.get(text, "")


def int_value(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def next_release_day(day: date, weekday_only: bool = True) -> date:
    """Snap `day` forward onto a Monday-Friday if it falls on a weekend.

    Does not advance a weekday. Saturday/Sunday become Monday.
    """
    cursor = day
    if weekday_only:
        while cursor.weekday() >= 5:
            cursor += timedelta(days=1)
    return cursor


def add_release_day(day: date, weekday_only: bool = True) -> date:
    """Advance one calendar day, then skip Saturday and Sunday.

    This is the canonical weekday pipeline step:
    Mon->Tue, Tue->Wed, Wed->Thu, Thu->Fri, Fri->Mon, Sat->Mon, Sun->Mon.
    """
    cursor = day + timedelta(days=1)
    return next_release_day(cursor, weekday_only)


def advance_to_next_weekday(day: date) -> date:
    """Canonical alias for the weekday pipeline step. Same as add_release_day."""
    return add_release_day(day, weekday_only=True)


def is_weekday(day: date) -> bool:
    return day.weekday() < 5


def tier_dates_from_inner(inner: date) -> dict[str, date]:
    """Inner Disciple date plus Path Initiate +7d and Royal Road +14d."""
    inner = next_release_day(inner, weekday_only=True)
    return {
        "innerDiscipleDate": inner,
        "pathInitiateDate": inner + timedelta(days=7),
        "royalRoadDate": inner + timedelta(days=14),
    }


def weekday_sequence(start: date, count: int) -> list[date]:
    """Return `count` consecutive Monday-Friday dates starting at `start` (snapped)."""
    cursor = next_release_day(start, weekday_only=True)
    out = [cursor]
    while len(out) < count:
        cursor = add_release_day(cursor, weekday_only=True)
        out.append(cursor)
    return out


def occupied_dates_from_assignments(
    assignments: list[dict[str, Any]],
    *,
    abbr: str = "",
    date_key: str = "innerDiscipleDate",
) -> set[date]:
    occupied: set[date] = set()
    wanted = normalize_novel(abbr, allow_all=False) if abbr else ""
    for item in assignments:
        if not isinstance(item, dict):
            continue
        item_abbr = normalize_novel(item.get("abbr") or item.get("novelAbbr"), allow_all=False)
        if wanted and item_abbr != wanted:
            continue
        parsed = parse_date(item.get(date_key))
        if parsed:
            occupied.add(parsed)
    return occupied


def max_existing_date(dates: set[date] | list[date] | None) -> date | None:
    values = [item for item in (dates or []) if isinstance(item, date)]
    if not values:
        return None
    return max(values)


def propose_inner_disciple_date(
    *,
    today: date,
    previous_inner: date | None = None,
    existing_future_inners: set[date] | list[date] | None = None,
    occupied_inner: set[date] | None = None,
) -> date:
    """Next Inner Disciple date from the existing queue, not from a today-only restart.

    Priority:
    1. Continue from the previous chapter's Inner Disciple weekday.
    2. Never schedule before tomorrow's next valid weekday.
    3. Append after the latest already-queued future Inner Disciple date.
    4. Skip occupied weekdays. Never land on Saturday or Sunday.
    """
    occupied = set(occupied_inner or [])
    existing = set(existing_future_inners or [])
    floor = next_release_day(today + timedelta(days=1), weekday_only=True)
    if previous_inner:
        candidate = add_release_day(previous_inner, weekday_only=True)
    else:
        candidate = floor
    if candidate < floor:
        candidate = floor
    queue_max = max_existing_date(existing)
    if queue_max is not None:
        after_queue = add_release_day(queue_max, weekday_only=True)
        if candidate < after_queue:
            candidate = after_queue
    guard = 0
    while candidate.weekday() >= 5 or candidate in occupied:
        candidate += timedelta(days=1)
        guard += 1
        if guard > 370:
            raise ValueError("Could not find an unoccupied Monday-Friday Inner Disciple date.")
    return candidate


def propose_release_dates(
    *,
    today: date,
    previous_inner: date | None = None,
    existing_future_inners: set[date] | list[date] | None = None,
    occupied_inner: set[date] | None = None,
    occupied_path: set[date] | None = None,
    occupied_royal: set[date] | None = None,
    already_scheduled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute or preserve Inner Disciple / Path Initiate / Royal Road dates.

    Existing valid dates are preserved. Missing tiers are derived from Inner
    Disciple. Date conflicts fail closed instead of inventing a duplicate slot.
    """
    scheduled = already_scheduled or {}
    existing_inner = parse_date(scheduled.get("innerDiscipleDate"))
    existing_path = parse_date(scheduled.get("pathInitiateDate"))
    existing_royal = parse_date(scheduled.get("royalRoadDate"))
    if existing_inner:
        inner = existing_inner
        preserved = True
    else:
        inner = propose_inner_disciple_date(
            today=today,
            previous_inner=previous_inner,
            existing_future_inners=existing_future_inners,
            occupied_inner=occupied_inner,
        )
        preserved = False
    derived = tier_dates_from_inner(inner)
    path = existing_path or derived["pathInitiateDate"]
    royal = existing_royal or derived["royalRoadDate"]
    conflicts: list[str] = []
    if inner.weekday() >= 5:
        conflicts.append("INNER_DISCIPLE_WEEKEND")
    if path.weekday() >= 5:
        conflicts.append("PATH_INITIATE_WEEKEND")
    if royal.weekday() >= 5:
        conflicts.append("ROYAL_ROAD_WEEKEND")
    if not existing_inner and inner in set(occupied_inner or []):
        conflicts.append("INNER_DISCIPLE_OCCUPIED")
    if not existing_path and path in set(occupied_path or []):
        conflicts.append("PATH_INITIATE_OCCUPIED")
    if not existing_royal and royal in set(occupied_royal or []):
        conflicts.append("ROYAL_ROAD_OCCUPIED")
    if path != inner + timedelta(days=7):
        conflicts.append("PATH_INITIATE_OFFSET")
    if royal != inner + timedelta(days=14):
        conflicts.append("ROYAL_ROAD_OFFSET")
    return {
        "innerDiscipleDate": inner.isoformat(),
        "pathInitiateDate": path.isoformat(),
        "royalRoadDate": royal.isoformat(),
        "preservedExisting": preserved,
        "ok": not conflicts,
        "conflicts": conflicts,
    }


def dates_for_new_queue_chapter(
    *,
    today: date,
    existing_assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Next Inner/Path/RR dates after the latest already-queued chapter.

    Existing assignment dates are not modified. The next chapter is appended
    after the last Inner Disciple weekday in `existing_assignments`.
    """
    inners: set[date] = set()
    last_inner: date | None = None
    last_chapter = -1
    for item in existing_assignments:
        if not isinstance(item, dict):
            continue
        chapter = int_value(item.get("chapter") or item.get("chapterNumber"))
        inner = parse_date(item.get("innerDiscipleDate"))
        if inner:
            inners.add(inner)
        if inner and chapter >= last_chapter:
            last_chapter = chapter
            last_inner = inner
    return propose_release_dates(
        today=today,
        previous_inner=last_inner,
        existing_future_inners=inners,
        occupied_inner=inners,
    )


def assignment_key(abbr: str, chapter: int) -> str:
    return f"{abbr}-{int(chapter)}"


def existing_assignment_for_chapter(
    assignments: list[dict[str, Any]],
    abbr: str,
    chapter: int,
) -> dict[str, Any] | None:
    wanted = normalize_novel(abbr, allow_all=False)
    number = int_value(chapter)
    for item in assignments:
        if not isinstance(item, dict):
            continue
        item_abbr = normalize_novel(item.get("abbr") or item.get("novelAbbr"), allow_all=False)
        if item_abbr == wanted and int_value(item.get("chapter") or item.get("chapterNumber")) == number:
            return item
    return None


def build_release_plan_rows(
    request: ReleasePlanRequest,
    *,
    novel_names: dict[str, str],
    chapter_indexes: dict[str, list[dict[str, Any]]],
    current_upload_chapters: dict[str, int | None],
) -> tuple[list[ReleasePlanRow], list[dict[str, Any]]]:
    selected = list(novel_names) if request.novel == "ALL" else [request.novel]
    rows: list[ReleasePlanRow] = []
    warnings: list[dict[str, Any]] = []
    for abbr in selected:
        if abbr not in novel_names:
            warnings.append({"abbr": abbr, "reason": "Unknown novel."})
            continue
        start = request.start_chapter or int_value(current_upload_chapters.get(abbr)) or 1
        through = int_value(request.targets.get(abbr)) or request.release_through_chapter
        if through < start:
            warnings.append({
                "abbr": abbr,
                "startChapter": start,
                "releaseThroughChapter": through,
                "reason": "Release-through chapter is before the current upload chapter.",
            })
            continue
        index_by_number = {
            int_value(item.get("number") or item.get("chapter") or item.get("chapterNumber")): item
            for item in chapter_indexes.get(abbr, [])
            if int_value(item.get("number") or item.get("chapter") or item.get("chapterNumber")) > 0
        }
        cursor = next_release_day(request.first_inner_disciple_date, request.weekday_only)
        for chapter in range(start, through + 1):
            source = index_by_number.get(chapter)
            if not source:
                warnings.append({
                    "abbr": abbr,
                    "chapter": chapter,
                    "reason": f"Chapter {chapter} is missing from the GitHub chapter index.",
                })
                continue
            path_date = cursor + timedelta(days=7)
            royal_date = cursor + timedelta(days=14)
            title = str(source.get("title") or source.get("heading") or f"Chapter {chapter}").strip()
            rows.append(ReleasePlanRow(
                release_plan_id=f"{abbr}-{chapter}-{cursor.isoformat()}",
                novel_id=abbr,
                novel_abbr=abbr,
                novel=novel_names[abbr],
                chapter_number=chapter,
                chapter_title=title,
                chapter_source_path=str(source.get("path") or source.get("sourcePath") or source.get("file") or ""),
                inner_disciple_date=cursor.isoformat(),
                path_initiate_date=path_date.isoformat(),
                royal_road_date=royal_date.isoformat(),
                notes=request.notes,
            ))
            cursor = add_release_day(cursor, request.weekday_only)
    rows.sort(key=lambda row: (row.inner_disciple_date, row.novel_abbr, row.chapter_number))
    return rows, warnings


def validate_stage_status(value: str) -> str:
    status = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported release planner status: {value}")
    return status


def release_stage_due_targets(
    assignments: list[dict[str, Any]],
    *,
    today: date | str | None = None,
    include_prepared: bool = False,
    include_scheduled: bool = False,
) -> list[dict[str, Any]]:
    if today is None:
        target_date = date.today()
    elif isinstance(today, date):
        target_date = today
    else:
        parsed = parse_date(today)
        if not parsed:
            raise ValueError("Today must be a valid ISO date.")
        target_date = parsed

    stage_rules = [
        ("inner_disciple", "innerDiscipleDate", "innerPosted", "innerPrepared"),
        ("path_initiate", "pathInitiateDate", "pathPosted", "pathPrepared"),
        ("royal_road", "royalRoadDate", "royalRoadPosted", "royalRoadPrepared"),
    ]
    targets: list[dict[str, Any]] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        key = str(assignment.get("key") or "").strip()
        abbr = normalize_novel(assignment.get("abbr") or assignment.get("novelAbbr"), allow_all=False)
        chapter = int_value(assignment.get("chapter") or assignment.get("chapterNumber"))
        if not key:
            key = f"{abbr}-{chapter}" if abbr and chapter > 0 else ""
        if not key:
            continue
        for stage, date_key, posted_key, prepared_key in stage_rules:
            due_date = parse_date(assignment.get(date_key))
            if not due_date or (not include_scheduled and due_date > target_date):
                continue
            posted = bool(assignment.get(posted_key))
            if stage == "royal_road" and assignment.get("needsRoyalRoadReview"):
                posted = False
            if posted:
                continue
            if assignment.get(prepared_key) and not include_prepared:
                continue
            targets.append({
                "key": key,
                "stage": stage,
                "abbr": abbr,
                "chapter": chapter,
                "date": due_date.isoformat(),
                "prepared": bool(assignment.get(prepared_key)),
                "scheduled": due_date > target_date,
                "needsRoyalRoadReview": bool(assignment.get("needsRoyalRoadReview")),
            })
    targets.sort(key=lambda item: (
        item["date"],
        {"inner_disciple": 0, "path_initiate": 1, "royal_road": 2}.get(item["stage"], 9),
        item["abbr"],
        item["chapter"],
    ))
    return targets
