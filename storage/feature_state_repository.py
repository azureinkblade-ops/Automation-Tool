"""Feature-state repository for deep-tiktok-rotation (SC-4, minimum-risk).

Mirrors app.py load_deep_tiktok_rotation defaults. Stores the payload in
state_snapshots.deepTikTokRotation. No app.py edits here; the app call-site
rewiring is part of the SC-4 handoff.

Concurrency: versioned via state_snapshots.deepTikTokRotation.version with
optimistic write guard.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import automation_db
from automation_db import connect, init_db, loads_json, dumps_json, utc_now_text

STATE_KEY = "deepTikTokRotation"
VERSION_KEY = "deepTikTokRotation.version"
MIGRATION_FLAG_KEY = "deep_tiktok_rotation_json_import_complete"
NOVEL_ABBRS = ["EN", "HA", "SF", "HP"]


class FeatureStateConflict(Exception):
    pass


@dataclass
class FeatureState:
    payload: Dict[str, Any]
    version: int

    def to_dict(self) -> Dict[str, Any]:
        return {"payload": self.payload, "version": self.version}


def default_payload() -> Dict[str, Any]:
    return {
        "schemaVersion": 1,
        "cycle": 1,
        "remainingNovels": [],
        "usedChapters": {abbr: [] for abbr in NOVEL_ABBRS},
        "history": [],
        "pending": None,
    }


def normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(data or {})
    data.setdefault("schemaVersion", 1)
    data.setdefault("cycle", 1)
    data.setdefault("remainingNovels", [])
    data.setdefault("usedChapters", {})
    data.setdefault("history", [])
    data.setdefault("pending", None)
    for abbr in NOVEL_ABBRS:
        values = data["usedChapters"].setdefault(abbr, [])
        data["usedChapters"][abbr] = sorted(
            {int(v) for v in values if str(v).lstrip("-").isdigit()}
        )
    return data


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


def load(root: Path) -> FeatureState:
    raw = automation_db.load_state_snapshot(root, STATE_KEY)
    if raw is None:
        return FeatureState(payload=default_payload(), version=0)
    raw.pop("_source", None)
    return FeatureState(payload=normalize(raw), version=_read_version(root))


def save(root: Path, payload: Dict[str, Any], expected_version: Optional[int] = None) -> FeatureState:
    payload = normalize(payload)
    init_db(root)
    current = _read_version(root)
    if expected_version is not None and expected_version != current:
        raise FeatureStateConflict(f"expected {expected_version}, found {current}")
    new_version = current + 1
    with connect(root) as conn:
        res = conn.execute(
            """
            UPDATE state_snapshots
            SET payload_json=?, updated_at=?
            WHERE state_key=?
              AND (SELECT CAST(payload_json AS INTEGER) FROM state_snapshots WHERE state_key=?)
              = ?
            """,
            (dumps_json(payload), utc_now_text(), STATE_KEY, VERSION_KEY, current),
        )
        if res.rowcount == 0:
            conn.execute(
                """
                INSERT INTO state_snapshots(state_key, payload_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (STATE_KEY, dumps_json(payload), utc_now_text()),
            )
        conn.commit()
    _write_version(root, new_version)
    return FeatureState(payload=payload, version=new_version)


def migration_status(root: Path) -> Dict[str, Any]:
    flag = automation_db.load_state_snapshot(root, MIGRATION_FLAG_KEY)
    return {
        "import_complete": flag is not None,
        "version": _read_version(root),
        "has_payload": automation_db.load_state_snapshot(root, STATE_KEY) is not None,
    }


def record_import_marker(root: Path, source_hash: str, app_commit: str) -> None:
    automation_db.upsert_state_snapshot(
        root,
        MIGRATION_FLAG_KEY,
        {"completed_at": utc_now_text(), "source_hash": source_hash, "app_commit": app_commit},
    )


def canonical_hash(payload: Dict[str, Any]) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
