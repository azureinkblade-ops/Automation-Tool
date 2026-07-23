"""Generic root-state repository (SC-7 cleanup / Group A conversion).

Most "root JSON" app state is already dual-written to `state_snapshots` via the
Phase-2 `_phase2_save_blob` system. The files handled here are the genuinely
FILE-ONLY ones (read via `read_json_safe`, no `state_snapshots` row yet):
automaticMetricsState, releaseAutomationState, storyHookChatgptResult,
pinnedContentPlan, pinnedProfileAssets, analyticsLab, youtubeEndScreenPlan,
youtubeEndScreenState, appRegressionDashboard.

This repository stores each under a `state_snapshots` key (camelCase logical
name), mirroring schedule_repository. It NEVER touches the live JSON file after
cutover, but provides a fail-soft fallback so behavior is preserved during the
transition: if the DB read fails, fall back to the file; if the file is absent,
return the provided default.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

import automation_db
from automation_db import connect, init_db, loads_json, dumps_json, utc_now_text

# Logical state_key for each converted root file.
KEYS = {
    "automaticMetricsState": "automaticMetricsState",
    "releaseAutomationState": "releaseAutomationState",
    "storyHookChatgptResult": "storyHookChatgptResult",
    "pinnedContentPlan": "pinnedContentPlan",
    "pinnedProfileAssets": "pinnedProfileAssets",
    "analyticsLab": "analyticsLab",
    "youtubeEndScreenPlan": "youtubeEndScreenPlan",
    "youtubeEndScreenState": "youtubeEndScreenState",
    "appRegressionDashboard": "appRegressionDashboard",
}


def _ensure_row(root: Path, key: str, default: Any) -> None:
    init_db(root)
    with connect(root) as conn:
        conn.execute(
            """
            INSERT INTO state_snapshots(state_key, payload_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(state_key) DO NOTHING
            """,
            (key, dumps_json(default), utc_now_text()),
        )
        conn.commit()


def load(root: Path, file_constant: str, default: Any = None,
         fallback_file: Optional[Path] = None) -> Any:
    """Load a root-state blob from state_snapshots.

    Fail-soft: on any DB error, fall back to `fallback_file` (the legacy JSON),
    then to `default`.
    """
    key = KEYS.get(file_constant)
    if key is None:
        raise KeyError(f"unknown root-state file constant: {file_constant}")
    try:
        init_db(root)
        row = automation_db.load_state_snapshot(root, key)
        if row is not None:
            return row
    except Exception:
        pass
    # fall back to legacy file
    if fallback_file is not None and fallback_file.exists():
        try:
            return loads_json(fallback_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save(root: Path, file_constant: str, data: Any,
         fallback_file: Optional[Path] = None) -> None:
    """Persist a root-state blob to state_snapshots (DB-first).

    Optionally mirrors to `fallback_file` during transition; once cutover is
    verified, callers should pass fallback_file=None.
    """
    key = KEYS.get(file_constant)
    if key is None:
        raise KeyError(f"unknown root-state file constant: {file_constant}")
    automation_db.upsert_state_snapshot(root, key, data)
    if fallback_file is not None:
        try:
            fallback_file.write_text(dumps_json(data), encoding="utf-8")
        except Exception:
            pass
