"""Generic root-state repository (SC-7 cleanup / Group A + Phase-3 retirement).

Most "root JSON" app state is already dual-written to `state_snapshots` via the
Phase-2 `_phase2_save_blob` system, or lives in dedicated tables (release_status).
The files handled here are the genuinely FILE-ONLY ones (read via
`read_json_safe`, no `state_snapshots` row yet): automaticMetricsState,
releaseAutomationState, storyHookChatgptResult, pinnedContentPlan,
pinnedProfileAssets, analyticsLab, youtubeEndScreenPlan, youtubeEndScreenState,
appRegressionDashboard.

This repository stores each under a `state_snapshots` key (camelCase logical
name), mirroring schedule_repository. It NEVER touches the live JSON file after
cutover, but provides a fail-soft fallback so behavior is preserved during the
transition: if the DB read fails, fall back to `fallback_file` (the legacy JSON),
then to `default`.

Phase-3 guardrails (approved 2026-07-23):
- Large blobs (analytics-lab 891KB, youtube-comment-queue 162KB, release_status
  148KB) are stored in SQLite like everything else. They are NOT loaded at
  startup and NOT included in broad "load all state" reads.
- `metadata()` selects state_key, updated_at and payload byte size only.
- `load()` parses JSON only after the owning feature requests the record.
- `save()` is transactional (upsert) and logs payload SIZE only, never content.
- Backups go through the SQLite backup API, not JSON mirrors.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import automation_db
from automation_db import loads_json, dumps_json

logger = logging.getLogger("root_state_repository")

# Logical state_key for each converted root file.
KEYS = {
    "automaticMetricsState": "automaticMetricsState",
    "releaseAutomationState": "releaseAutomationState",
    "storyHookChatgptResult": "storyHookChatgptResult",
    "pinnedContentPlan": "pinnedContentPlan",
    "pinnedProfileAssets": "pinnedProfileAssets",
    "analyticsLab": "analyticsLab",
    "youtubeCommentQueue": "youtubeCommentQueue",
    "youtubeEndScreenPlan": "youtubeEndScreenPlan",
    "youtubeEndScreenState": "youtubeEndScreenState",
    "appRegressionDashboard": "appRegressionDashboard",
}


def _key(file_constant: str) -> str:
    key = KEYS.get(file_constant)
    if key is None:
        raise KeyError(f"unknown root-state file constant: {file_constant}")
    return key


def metadata(root: Path, file_constant: str) -> Optional[Dict[str, Any]]:
    """Return {state_key, updated_at, size_bytes} WITHOUT parsing the payload.

    Used for listing/health checks so large blobs are never deserialized.
    """
    key = _key(file_constant)
    try:
        row = (
            automation_db.connect(root)
            .execute(
                "SELECT state_key, updated_at, length(payload_json) AS size_bytes "
                "FROM state_snapshots WHERE state_key=?",
                (key,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return {
            "state_key": row["state_key"],
            "updated_at": row["updated_at"],
            "size_bytes": row["size_bytes"],
        }
    except Exception as exc:
        logger.warning("metadata(%s) failed: %s", key, exc)
        return None


def load(root: Path, file_constant: str, default: Any = None,
         fallback_file: Optional[Path] = None) -> Any:
    """Load a root-state blob from state_snapshots.

    Fail-soft: on any DB error, fall back to `fallback_file` (the legacy JSON),
    then to `default`. JSON is parsed ONLY here, after an explicit request.
    """
    key = _key(file_constant)
    try:
        row = automation_db.load_state_snapshot(root, key)
        if row is not None:
            if isinstance(row, dict):
                row.pop("_source", None)
            return row
    except Exception as exc:
        logger.warning("load(%s) DB failed, trying fallback: %s", key, exc)
    if fallback_file is not None and fallback_file.exists():
        try:
            return loads_json(fallback_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("load(%s) fallback file failed: %s", key, exc)
    return default


def save(root: Path, file_constant: str, data: Any,
         fallback_file: Optional[Path] = None) -> None:
    """Persist a root-state blob to state_snapshots (DB-first, transactional).

    Logs payload SIZE only (never content). Optionally mirrors to
    `fallback_file` during transition; once cutover is verified, callers pass
    fallback_file=None.
    """
    key = _key(file_constant)
    payload = dumps_json(data)
    logger.info("save(%s): payload_size_bytes=%d", key, len(payload))
    automation_db.upsert_state_snapshot(root, key, data)
    if fallback_file is not None:
        try:
            fallback_file.write_text(payload, encoding="utf-8")
        except Exception as exc:
            logger.warning("save(%s) fallback file write skipped: %s", key, exc)
