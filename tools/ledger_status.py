"""Ledger status reporting — materialized vs reserved vs published.

Observability must never collapse to a single ledger max.
HA example: materialized=112, reserved=113 (writePending stub), published=None/0.
written novel_chapters / ledger rows are MATERIALIZED even if a stale
writePending stub remains (fail closed; do not promote over manual canon).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union


LEDGER_STATUS_VERSION = "ledger_status_v1"


@dataclass
class LedgerStatus:
    """Split chapter watermark — never a single max."""

    latest_materialized_chapter: Optional[int] = None
    latest_reserved_chapter: Optional[int] = None
    latest_published_chapter: Optional[int] = None
    write_pending_without_materialization: List[int] = field(default_factory=list)
    novel_id: Optional[str] = None
    abbr: Optional[str] = None
    version: str = LEDGER_STATUS_VERSION
    # Precise membership (optional; filled by compute helpers; omitted from to_dict)
    _materialized_set: Optional[set] = field(default=None, repr=False, compare=False)
    _reserved_set: Optional[set] = field(default=None, repr=False, compare=False)
    _published_set: Optional[set] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "latest_materialized_chapter": self.latest_materialized_chapter,
            "latest_reserved_chapter": self.latest_reserved_chapter,
            "latest_published_chapter": self.latest_published_chapter,
            "write_pending_without_materialization": list(
                self.write_pending_without_materialization
            ),
            "novel_id": self.novel_id,
            "abbr": self.abbr,
            "version": self.version,
        }

    def chapter_availability(self, chapter: int) -> str:
        ch = int(chapter)
        mat_set = self._materialized_set
        reserved_set = self._reserved_set
        published_set = self._published_set

        if published_set is not None and ch in published_set:
            return "PUBLISHED"
        if mat_set is not None and ch in mat_set:
            return "MATERIALIZED"
        if ch in self.write_pending_without_materialization:
            return "RESERVED_WRITE_PENDING"
        if reserved_set is not None and ch in reserved_set and (
            mat_set is None or ch not in mat_set
        ):
            return "RESERVED_WRITE_PENDING"

        # Watermark fallbacks when precise sets absent
        if self.latest_published_chapter is not None and ch == int(self.latest_published_chapter):
            return "PUBLISHED"
        if self.latest_materialized_chapter is not None and ch == int(
            self.latest_materialized_chapter
        ):
            return "MATERIALIZED"
        if self.latest_reserved_chapter is not None and ch == int(self.latest_reserved_chapter):
            mat = self.latest_materialized_chapter
            if mat is None or ch > int(mat):
                return "RESERVED_WRITE_PENDING"
        return "FREE"

    def is_ledger_clean_for_allocate(self, candidate_chapter: int) -> bool:
        return self.chapter_availability(int(candidate_chapter)) == "FREE"


@dataclass
class NextChapterSelection:
    chapter_number: int
    chapter_id: str
    mode: str  # RECONCILE | ALLOCATE
    availability: str
    reason: str
    ledger_status: LedgerStatus

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "chapter_id": self.chapter_id,
            "mode": self.mode,
            "availability": self.availability,
            "reason": self.reason,
            "ledger_status": self.ledger_status.to_dict(),
        }


def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _flag_true(value: Any) -> bool:
    """Fail-closed truthiness for written/writePending JSON flags.

    Accepts bool True, int 1, and common truthy strings. String "false" /
    "0" / "no" are False (unlike bare bool("false")).
    """
    if value is True or value is False:
        return bool(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"", "0", "false", "no", "off", "none", "null"}:
            return False
        return False
    return False


def _publication_true(payload: Mapping[str, Any]) -> bool:
    keys = (
        "postedToPatreon",
        "postedToRoyalRoad",
        "patreonPosted",
        "royalRoadPosted",
        "patreonInnerExists",
        "patreonPathExists",
        "royalRoadExists",
        "published",
    )
    for key in keys:
        if _flag_true(payload.get(key)):
            return True
    return False


def compute_ledger_status_from_structured(
    *,
    novel_id: str,
    abbr: Optional[str] = None,
    materialized_chapters: Iterable[int] = (),
    ledger_entries: Sequence[Mapping[str, Any]] = (),
    published_chapters: Optional[Iterable[int]] = None,
) -> LedgerStatus:
    """Pure helper: structured inputs only (unit-test friendly).

    materialized_chapters: chapter numbers with novel_chapters row / written=true.
    ledger_entries: mappings with at least ``chapter`` and optional writePending/written/
    publication flags. May also pass ``payload`` nested dict.
    """
    mat_set = {int(n) for n in materialized_chapters if _as_int(n) is not None}
    reserved_set: set[int] = set()
    published_set: set[int] = set()
    write_pending_no_mat: List[int] = []

    if published_chapters is not None:
        published_set = {int(n) for n in published_chapters if _as_int(n) is not None}

    for entry in ledger_entries:
        payload = dict(entry.get("payload") or {})
        for k, v in entry.items():
            if k not in {"chapter", "payload", "ledger_key", "abbr"} and k not in payload:
                payload[k] = v
        ch = _as_int(entry.get("chapter") if "chapter" in entry else payload.get("chapter"))
        if ch is None:
            continue
        written = _flag_true(payload.get("written"))
        write_pending = _flag_true(payload.get("writePending"))
        # written always wins: stale writePending stub must not hide materialization
        if written:
            mat_set.add(ch)
        if write_pending:
            reserved_set.add(ch)
            if ch not in mat_set and not written:
                write_pending_no_mat.append(ch)
        if published_chapters is None and _publication_true(payload):
            published_set.add(ch)
        # Any ledger row occupies the chapter number for allocation purposes
        reserved_set.add(ch)

    write_pending_no_mat = sorted(set(write_pending_no_mat))
    return LedgerStatus(
        latest_materialized_chapter=max(mat_set) if mat_set else None,
        latest_reserved_chapter=max(reserved_set) if reserved_set else None,
        latest_published_chapter=max(published_set) if published_set else None,
        write_pending_without_materialization=write_pending_no_mat,
        novel_id=novel_id,
        abbr=abbr or novel_id,
        _materialized_set=mat_set,
        _reserved_set=reserved_set,
        _published_set=published_set,
    )


def compute_ledger_status_from_db(
    db: Union[str, Path, sqlite3.Connection],
    *,
    novel_id: str,
    abbr: Optional[str] = None,
) -> LedgerStatus:
    """Load novel_chapters + chapter_ledger and return split status."""
    abbr_key = (abbr or novel_id).upper()
    own_conn = False
    if isinstance(db, sqlite3.Connection):
        con = db
    else:
        con = sqlite3.connect(str(db))
        own_conn = True
    try:
        con.row_factory = sqlite3.Row
        # Classify novel_chapters by payload written/writePending (fail closed):
        # - written=true  -> MATERIALIZED (even if writePending stub remains)
        # - writePending without written -> RESERVED stub (do NOT fake materialize)
        # - legacy row (no active pending) -> MATERIALIZED for backward compat
        mat_rows = con.execute(
            "SELECT chapter_number, payload_json FROM novel_chapters "
            "WHERE novel_id=? OR chapter_id LIKE ?",
            (novel_id, f"{novel_id}-%"),
        ).fetchall()
        materialized: List[int] = []
        nc_stub_entries: List[Dict[str, Any]] = []
        for r in mat_rows:
            ch = _as_int(r["chapter_number"])
            if ch is None:
                continue
            try:
                nc_payload = json.loads(r["payload_json"] or "{}")
            except json.JSONDecodeError:
                nc_payload = {}
            if not isinstance(nc_payload, dict):
                nc_payload = {}
            nc_written = _flag_true(nc_payload.get("written"))
            nc_pending = _flag_true(nc_payload.get("writePending"))
            if nc_written:
                materialized.append(ch)
            elif nc_pending:
                nc_stub_entries.append(
                    {
                        "chapter": ch,
                        "ledger_key": f"{abbr_key}-{ch}",
                        "payload": {
                            "written": False,
                            "writePending": True,
                            "writeMode": nc_payload.get("writeMode"),
                        },
                    }
                )
            else:
                # Legacy inventory row without an active writePending reservation
                materialized.append(ch)

        pub_rows = con.execute(
            """
            SELECT chapter_number FROM novel_chapters
            WHERE (novel_id=? OR chapter_id LIKE ?)
              AND (
                COALESCE(patreon_inner_exists,0)=1
                OR COALESCE(patreon_path_exists,0)=1
                OR COALESCE(royal_road_exists,0)=1
              )
            """,
            (novel_id, f"{novel_id}-%"),
        ).fetchall()
        published = [int(r["chapter_number"]) for r in pub_rows if r["chapter_number"] is not None]

        ledger_rows = con.execute(
            "SELECT chapter, ledger_key, payload_json FROM chapter_ledger WHERE abbr=? OR ledger_key LIKE ?",
            (abbr_key, f"{abbr_key}-%"),
        ).fetchall()
        entries: List[Dict[str, Any]] = []
        for row in ledger_rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            entries.append(
                {
                    "chapter": row["chapter"],
                    "ledger_key": row["ledger_key"],
                    "payload": payload,
                }
            )
            if _publication_true(payload):
                ch = _as_int(row["chapter"])
                if ch is not None:
                    published.append(ch)

        # novel_chapters writePending stubs merge into ledger_entries so status
        # treats them as RESERVED; chapter_ledger written=true still wins later.
        if nc_stub_entries:
            entries.extend(nc_stub_entries)

        return compute_ledger_status_from_structured(
            novel_id=novel_id,
            abbr=abbr_key,
            materialized_chapters=materialized,
            ledger_entries=entries,
            published_chapters=published,
        )
    finally:
        if own_conn:
            con.close()


def select_next_missing_chapter(
    status: LedgerStatus,
    *,
    novel_id: Optional[str] = None,
) -> NextChapterSelection:
    """Prefer writePending reservation without novel_chapters row → RECONCILE.

    Do not allocate max+1 when a reservation exists for that next number.
    """
    nid = novel_id or status.novel_id or status.abbr or "XX"
    pending = list(status.write_pending_without_materialization)
    if pending:
        ch = int(min(pending))
        return NextChapterSelection(
            chapter_number=ch,
            chapter_id=f"{nid}-{ch}",
            mode="RECONCILE",
            availability="RESERVED_WRITE_PENDING",
            reason="write_pending_reservation_without_materialization",
            ledger_status=status,
        )

    mat = status.latest_materialized_chapter or 0
    reserved = status.latest_reserved_chapter or 0
    candidate = max(mat, reserved) + 1
    reserved_set = status._reserved_set or set()
    mat_set = status._materialized_set or set()
    while candidate in reserved_set or candidate in mat_set:
        candidate += 1

    return NextChapterSelection(
        chapter_number=candidate,
        chapter_id=f"{nid}-{candidate}",
        mode="ALLOCATE",
        availability="FREE",
        reason="next_after_materialized_and_reserved",
        ledger_status=status,
    )


def preflight_chapter_gate(
    status: LedgerStatus,
    *,
    candidate_chapter: int,
    mode: str = "ALLOCATE",
) -> Dict[str, Any]:
    """Canary/preflight gate — never claim ledger clean when reservation holds the number.

    mode=ALLOCATE: RESERVED_WRITE_PENDING means not free.
    mode=RECONCILE: reservation is expected; MATERIALIZED/PUBLISHED block.
    """
    availability = status.chapter_availability(int(candidate_chapter))
    ledger_clean_for_allocate = availability == "FREE"
    mode_u = mode.upper()
    if mode_u == "RECONCILE":
        already = availability in {"MATERIALIZED", "PUBLISHED"}
        chapter_already_exists = "YES" if already else "NO"
        ok = not already
        reason = None if ok else f"chapter_{availability.lower()}"
    else:
        already = availability != "FREE"
        chapter_already_exists = "YES" if already else "NO"
        ok = not already
        reason = None if ok else f"chapter_{availability.lower()}"

    return {
        "LATEST_MATERIALIZED_CHAPTER": status.latest_materialized_chapter,
        "LATEST_RESERVED_CHAPTER": status.latest_reserved_chapter,
        "LATEST_PUBLISHED_CHAPTER": status.latest_published_chapter or 0,
        "CHAPTER_AVAILABILITY": availability,
        "CHAPTER_ALREADY_EXISTS": chapter_already_exists,
        "LEDGER_CLEAN_FOR_ALLOCATE": "YES" if ledger_clean_for_allocate else "NO",
        "MODE": mode_u,
        "OK": ok,
        "failure_reason": reason,
        "ledger_status": status.to_dict(),
    }
