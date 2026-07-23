"""Posting schedule repository for the SQLite cutover (SC-3, minimum-risk).

Stores the exact nested schedule payload in state_snapshots under
`postingSchedule`, plus a version marker under `postingSchedule.version`.
Runtime code must use this repository instead of reading/writing
posting_schedule.json.

Concurrency: save() accepts expected_version. A stale version raises
ScheduleVersionConflict and does NOT overwrite.

This module never touches the live JSON file. Migration is performed by
tools/migrate_posting_schedule.py.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import automation_db
from automation_db import connect, init_db, loads_json, dumps_json, utc_now_text

SCHEDULE_KEY = "postingSchedule"
VERSION_KEY = "postingSchedule.version"
MIGRATION_FLAG_KEY = "posting_schedule_json_import_complete"


class ScheduleVersionConflict(Exception):
    """Raised when expected_version does not match the stored version."""


class ScheduleValidationError(Exception):
    """Raised when the schedule payload fails structural validation."""


@dataclass
class VersionedPostingSchedule:
    payload: Dict[str, Any]
    version: int
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload": self.payload,
            "version": self.version,
            "updated_at": self.updated_at,
        }


def validate(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ScheduleValidationError("payload must be an object")
    if "novels" not in payload:
        raise ScheduleValidationError("payload missing 'novels'")
    novels = payload["novels"]
    if not isinstance(novels, list) or not novels:
        raise ScheduleValidationError("'novels' must be a non-empty array")
    for novel in novels:
        if not isinstance(novel, dict) or "abbr" not in novel:
            raise ScheduleValidationError("each novel must have 'abbr'")


def _read_version(root: Path) -> int:
    with connect(root) as conn:
        row = conn.execute(
            "SELECT payload_json FROM state_snapshots WHERE state_key=? LIMIT 1",
            (VERSION_KEY,),
        ).fetchone()
    if not row:
        return 0
    try:
        return int(loads_json(row["payload_json"]))
    except Exception:
        return 0


def _write_version(root: Path, version: int) -> None:
    with connect(root) as conn:
        conn.execute(
            """
            INSERT INTO state_snapshots(state_key, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
            """,
            (VERSION_KEY, dumps_json(version), utc_now_text()),
        )


def load(root: Path) -> Optional[VersionedPostingSchedule]:
    payload = automation_db.load_state_snapshot(root, SCHEDULE_KEY)
    if payload is None:
        return None
    payload.pop("_source", None)
    return VersionedPostingSchedule(
        payload=payload,
        version=_read_version(root),
        updated_at=utc_now_text(),
    )


def create_default() -> Dict[str, Any]:
    """Default schedule matching the prior app default (4 novels, weekday releases)."""
    from datetime import date

    today = date.today().isoformat()
    novels = [
        {"abbr": abbr, "name": name, "currentRoyalRoadChapter": 0, "nextChapter": 1,
         "nextRoyalRoadDate": today, "startDate": today,
         "releaseDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
        for abbr, name in [
            ("EN", "Eternal Nexus"), ("HA", "Heavenly Ascension System"),
            ("SF", "Soul Forge Era"), ("HP", "Hundredfold Path"),
        ]
    ]
    return {
        "chapterReleaseDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "generalPromoDays": ["Tuesday", "Thursday", "Saturday"],
        "royalRoadDelayDays": 14,
        "releaseQueueStartDate": today,
        "chapterReleaseTime": "09:00",
        "patreonEarlyAccessDays": [14, 7],
        "generalPromoRotation": ["YouTube", "Royal Road", "TikTok"],
        "novels": novels,
    }


def save(root: Path, payload: Dict[str, Any], expected_version: Optional[int] = None) -> VersionedPostingSchedule:
    validate(payload)
    init_db(root)
    current = _read_version(root)
    if expected_version is not None and expected_version != current:
        raise ScheduleVersionConflict(
            f"expected version {expected_version}, found {current}"
        )
    new_version = current + 1
    with connect(root) as conn:
        # Optimistic concurrency at the SQL level.
        res = conn.execute(
            """
            UPDATE state_snapshots
            SET payload_json=?, updated_at=?
            WHERE state_key=?
              AND (SELECT CAST(payload_json AS INTEGER) FROM state_snapshots WHERE state_key=?)
            = ?
            """,
            (dumps_json(payload), utc_now_text(), SCHEDULE_KEY, VERSION_KEY, current),
        )
        if res.rowcount == 0:
            # Either the payload row or version row missing; ensure both exist.
            conn.execute(
                """
                INSERT INTO state_snapshots(state_key, payload_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (SCHEDULE_KEY, dumps_json(payload), utc_now_text()),
            )
        conn.commit()
    _write_version(root, new_version)
    return VersionedPostingSchedule(payload=payload, version=new_version, updated_at=utc_now_text())


def migration_status(root: Path) -> Dict[str, Any]:
    flag = automation_db.load_state_snapshot(root, MIGRATION_FLAG_KEY)
    return {
        "import_complete": flag is not None,
        "version": _read_version(root),
        "has_payload": automation_db.load_state_snapshot(root, SCHEDULE_KEY) is not None,
    }


def record_import_marker(root: Path, source_hash: str, item_count: int, app_commit: str) -> None:
    payload = {
        "completed_at": utc_now_text(),
        "source_hash": source_hash,
        "item_count": item_count,
        "app_commit": app_commit,
    }
    automation_db.upsert_state_snapshot(root, MIGRATION_FLAG_KEY, payload)


def canonical_hash(payload: Dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
