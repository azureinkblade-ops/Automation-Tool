"""YouTube build pipeline + pinned-comment queue (Task 7 of the extraction).

Extracts the YouTube subsystem surface: youtube_build_status (pack build-status probe)
and queue_youtube_pinned_comment (pinned-comment queue writer). The plan notes the YouTube
queue lock/thread live here; the lock is injected as a data collaborator (threading state
owned by app.py until Task 8).

Not-yet-extracted deps are injected via REQUIRED_COLLABORATORS with safe stubs; app.py
wires the real functions at Task 8. write_json_atomic/read_json_safe come from release_state
+ promo_copy; story_key from promo_copy; YOUTUBE_COMMENT_QUEUE_FILE from config.

Imports ONLY app_config, app_state, promo_copy, release_state, and any already-extracted
helpers. MUST NOT import app.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 7).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state  # noqa: F401 (reserved for future in-module locks/caches)
import promo_copy as copy
import release_state as rs

# Re-exported config constants used below.
ROOT = config.ROOT
YOUTUBE_COMMENT_QUEUE_FILE = config.YOUTUBE_COMMENT_QUEUE_FILE

# release_state provides the atomic JSON write.
write_json_atomic = rs.write_json_atomic
# promo_copy provides the pure helpers.
read_json_safe = copy.read_json_safe
story_key = copy.story_key


# --- not-yet-extracted collaborators (stubs; wired by app.py at Task 8) ---

REQUIRED_COLLABORATORS = [
    "resolve_youtube_pack_folder",
    "media_file_valid",
    "media_duration_seconds",
    "expected_youtube_min_duration",
    "youtube_pinned_comment_text",
    "load_youtube_comment_queue",
]

# threading.Lock runtime state (injected as data collaborator from app.py).
YOUTUBE_COMMENT_QUEUE_LOCK = None


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"youtube_pipeline: collaborator '{name}' not injected. "
            f"app.py must pass collaborators={{'{name}': <real fn>}} at Task 8."
        )
    return _fn


def _default_collaborators() -> dict[str, Any]:
    return {name: _stub_raise(name) for name in REQUIRED_COLLABORATORS}


# Module-global collaborator registry (see promo_builder for the convention).
_COLLAB: dict[str, Any] = _default_collaborators()


def set_collaborators(collab: dict[str, Any]) -> None:
    """Wire the real app.py functions (and data) into this module. Call once at startup."""
    global _COLLAB
    _COLLAB = dict(collab)


def get_collaborators() -> dict[str, Any]:
    return dict(_COLLAB)


def _get(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn


# --- youtube_build_status (verbatim; collaborators injected) ---

def youtube_build_status(folder_value: str, *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    folder = _get(collab, "resolve_youtube_pack_folder")(folder_value)
    status_file = folder / "youtube-build-status.json"
    output = folder / "youtube-video.mp4"
    payload = read_json_safe(status_file) if status_file.exists() else {}
    payload.update(
        {
            "folder": str(folder),
            "statusFile": str(status_file),
            "video": str(output),
            "videoExists": output.exists(),
            "videoValid": _get(collab, "media_file_valid")(output, "v:0"),
            "duration": _get(collab, "media_duration_seconds")(output) if output.exists() else 0.0,
            "minimumDuration": _get(collab, "expected_youtube_min_duration")(folder),
        }
    )
    started = payload.get("startedAt")
    if payload.get("running") and started:
        try:
            started_at = time.mktime(time.strptime(str(started), "%Y-%m-%d %H:%M:%S"))
            payload["elapsedSeconds"] = round(time.time() - started_at, 1)
        except Exception:
            pass
    return payload


# --- queue_youtube_pinned_comment (verbatim; collaborators injected) ---

def queue_youtube_pinned_comment(upload: dict[str, Any], *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    folder = str(upload.get("folder") or "")
    upload_id = str(upload.get("id") or "")
    metadata = upload.get("metadata") if isinstance(upload.get("metadata"), dict) else {}
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lock = YOUTUBE_COMMENT_QUEUE_LOCK
    if lock is None:
        lock = _NullLock()
    with lock:
        queue = _get(collab, "load_youtube_comment_queue")()
        library_backfill = upload_id.startswith("library-")
        existing = next(
            (
                item for item in queue["items"]
                if (upload_id and str(item.get("uploadId") or "") == upload_id)
                or (not library_backfill and str(item.get("folder") or "") == folder)
            ),
            None,
        )
        if existing is None:
            existing = {
                "id": hashlib.sha256(f"youtube-comment|{upload_id if library_backfill else folder}".encode("utf-8")).hexdigest()[:16],
                "createdAt": now,
                "attempts": 0,
                "status": "waiting_video_id",
            }
            queue["items"].append(existing)
        existing.update(
            {
                "uploadId": upload_id,
                "folder": folder,
                "abbr": story_key(str(metadata.get("abbr") or "")),
                "chapter": str(metadata.get("chapter") or ""),
                "title": str(upload.get("title") or metadata.get("title") or ""),
                "comment": str(upload.get("pinned_comment") or "").strip() or _get(collab, "youtube_pinned_comment_text")(metadata),
                "updatedAt": now,
            }
        )
        if existing.get("status") not in {"posted", "pinned"}:
            existing["status"] = "waiting_video_id" if not existing.get("videoId") else "waiting_public"
        queue["updatedAt"] = now
        write_json_atomic(YOUTUBE_COMMENT_QUEUE_FILE, queue)
        return dict(existing)


class _NullLock:
    """Fallback lock when YOUTUBE_COMMENT_QUEUE_LOCK is not injected (single-threaded tests)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
