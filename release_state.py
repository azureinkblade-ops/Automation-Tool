"""Release state + dual-store (JSON mirror + SQLite) writes (Task 3 of the extraction).

Holds the chapter-ledger and release-status state plus the JSON/SQLite mirror writes
(the critical dual-store seam the plan calls out). This module imports ONLY
``app_config`` (constants), ``app_state`` (locks/caches), ``automation_db`` (DB access),
and ``promo_copy`` (for story_key). It MUST NOT import ``app``.

The ledger load/save + update path is reproduced verbatim from app.py, including the
dual-store writes (JSON file + SQLite mirror) which are a required regression contract.

``release_status_for_chapter`` depends on wider release-status machinery that is not yet
extracted (novel_schedule_entry, chapter_release_dates, iso_today, load_release_status).
Those are injected as collaborators with safe stubs; Task 8 (inversion) wires the real
app functions. The pure dual-store ledger core is self-contained.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 3).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state
import automation_db
import promo_copy as copy

# Re-exported config constants used below.
ROOT = config.ROOT
OUTPUT_DIR = config.OUTPUT_DIR
SOCIAL_OUTPUT_DIR = config.SOCIAL_OUTPUT_DIR
TIKTOK_OUTPUT_DIR = config.TIKTOK_OUTPUT_DIR
YOUTUBE_OUTPUT_DIR = config.YOUTUBE_OUTPUT_DIR
CHAPTER_LEDGER_FILE = config.CHAPTER_LEDGER_FILE
RELEASE_STATUS_FILE = config.RELEASE_STATUS_FILE
NOVEL_NAMES = config.NOVEL_NAMES
CONTINUITY_DIR = config.CONTINUITY_DIR

# promo_copy provides story_key (pure).
story_key = copy.story_key

# app_state provides the per-file JSON write locks used by write_json_atomic.
JSON_WRITE_LOCKS = state.JSON_WRITE_LOCKS
JSON_WRITE_LOCKS_GUARD = state.JSON_WRITE_LOCKS_GUARD


# --- shared atomic JSON write (verbatim from app.py) ---

def json_write_lock(path: Path) -> threading.RLock:
    key = str(path.resolve()).lower()
    with JSON_WRITE_LOCKS_GUARD:
        lock = JSON_WRITE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            JSON_WRITE_LOCKS[key] = lock
        return lock


def write_json_atomic(path: Path, payload: Any, attempts: int = 8) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2)
    last_error: Exception | None = None
    with json_write_lock(path):
        for attempt in range(max(1, attempts)):
            temp_path = path.with_name(f"{path.name}.{os.getpid()}.{int(time.time() * 1000)}.{attempt}.tmp")
            try:
                temp_path.write_text(encoded, encoding="utf-8")
                os.replace(temp_path, path)
                return
            except PermissionError as exc:
                last_error = exc
                try:
                    temp_path.unlink()
                except OSError:
                    pass
                time.sleep(0.08 * (attempt + 1))
            except OSError as exc:
                last_error = exc
                try:
                    temp_path.unlink()
                except OSError:
                    pass
                time.sleep(0.08 * (attempt + 1))
    if last_error is not None:
        raise last_error


# --- dual-store mirror helpers (verbatim from app.py) ---

def mirror_post_record_to_database(record: dict[str, Any]) -> None:
    try:
        automation_db.upsert_post_record(ROOT, record)
    except Exception as exc:
        print(f"Database mirror failed for post record: {exc}", file=sys.stderr)


def mirror_chapter_ledger_to_database(entry: dict[str, Any]) -> None:
    try:
        automation_db.upsert_chapter_ledger_entry(ROOT, entry)
    except Exception as exc:
        print(f"Database mirror failed for chapter ledger: {exc}", file=sys.stderr)


def mirror_release_status_to_database(data: dict[str, Any]) -> None:
    try:
        automation_db.upsert_release_status(ROOT, data)
    except Exception as exc:
        print(f"Database mirror failed for release status: {exc}", file=sys.stderr)


def mirror_approval_cleared_to_database(key: str, record: dict[str, Any]) -> None:
    try:
        automation_db.upsert_approval_cleared(ROOT, key, record)
    except Exception as exc:
        print(f"Database mirror failed for approval item: {exc}", file=sys.stderr)


def mirror_recovery_event_to_database(event: dict[str, Any]) -> None:
    try:
        automation_db.insert_recovery_event(ROOT, event)
    except Exception as exc:
        print(f"Database mirror failed for recovery event: {exc}", file=sys.stderr)


def mirror_state_snapshot_to_database(key: str, payload: dict[str, Any]) -> None:
    try:
        automation_db.upsert_state_snapshot(ROOT, key, payload)
    except Exception as exc:
        print(f"Database mirror failed for {key}: {exc}", file=sys.stderr)


# --- chapter ledger (dual-store core) ---

def load_chapter_ledger() -> dict[str, Any]:
    try:
        data = automation_db.load_chapter_ledger(ROOT)
        if isinstance(data, dict) and isinstance(data.get("chapters"), dict) and data["chapters"]:
            return data
    except Exception as exc:
        print(f"Database read failed for chapter ledger: {exc}", file=sys.stderr)
    if not CHAPTER_LEDGER_FILE.exists():
        return {"schemaVersion": 1, "chapters": {}, "updatedAt": ""}
    try:
        data = json.loads(CHAPTER_LEDGER_FILE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"schemaVersion": 1, "chapters": {}, "updatedAt": ""}
    data.setdefault("schemaVersion", 1)
    data.setdefault("chapters", {})
    return data


def save_chapter_ledger(data: dict[str, Any]) -> None:
    data.setdefault("schemaVersion", 1)
    data.setdefault("chapters", {})
    data["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_atomic(CHAPTER_LEDGER_FILE, data)
    for entry in data.get("chapters", {}).values() if isinstance(data.get("chapters"), dict) else []:
        if isinstance(entry, dict):
            mirror_chapter_ledger_to_database(entry)


def chapter_ledger_default_entry(abbr: str, chapter_number: int) -> dict[str, Any]:
    return {
        "abbr": abbr,
        "novel": NOVEL_NAMES.get(abbr, abbr),
        "chapter": chapter_number,
        "title": "",
        "written": False,
        "uploadedToGitHubDocs": False,
        "githubDocsUploaded": False,
        "postedToPatreon": False,
        "postedToRoyalRoad": False,
        "patreonDraftPrepared": False,
        "royalRoadReviewed": False,
        "promoPackBuilt": False,
        "promoBuilt": False,
        "shortsReelsBuilt": False,
        "shortsPackBuilt": False,
        "youtubeFullVideoBuilt": False,
        "youtubePackBuilt": False,
        "socialPostsBuilt": False,
        "dailySocialBuilt": False,
        "socialPostsQueued": False,
        "instagramQueued": False,
        "bufferQueued": False,
        "folders": {},
        "updatedAt": "",
    }


def normalize_chapter_ledger_entry(abbr: str, chapter_number: int, entry: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = chapter_ledger_default_entry(abbr, chapter_number)
    normalized.update(entry or {})
    if normalized.get("githubDocsUploaded"):
        normalized["uploadedToGitHubDocs"] = True
    if normalized.get("uploadedToGitHubDocs"):
        normalized["githubDocsUploaded"] = True
    if normalized.get("promoBuilt"):
        normalized["promoPackBuilt"] = True
    if normalized.get("promoPackBuilt"):
        normalized["promoBuilt"] = True
    if normalized.get("shortsPackBuilt"):
        normalized["shortsReelsBuilt"] = True
    if normalized.get("shortsReelsBuilt"):
        normalized["shortsPackBuilt"] = True
    if normalized.get("shortsNeedsRebuild"):
        normalized["shortsReelsBuilt"] = False
        normalized["shortsPackBuilt"] = False
    folders = normalized.get("folders") if isinstance(normalized.get("folders"), dict) else {}
    shorts_folder = str(folders.get("shorts") or normalized.get("shortsFolder") or "").strip()
    if shorts_folder:
        try:
            if not (Path(shorts_folder) / "tiktok-video.mp4").exists():
                normalized["shortsReelsBuilt"] = False
                normalized["shortsPackBuilt"] = False
                normalized["shortsNeedsRebuild"] = True
                normalized.setdefault("shortsMissingReason", "Shorts folder exists but tiktok-video.mp4 is missing.")
        except Exception:
            pass
    if normalized.get("youtubeFullVideoBuilt"):
        normalized["youtubePackBuilt"] = True
    if normalized.get("dailySocialBuilt"):
        normalized["socialPostsBuilt"] = True
    if normalized.get("socialPostsBuilt"):
        normalized["dailySocialBuilt"] = True
    if normalized.get("instagramQueued") or normalized.get("bufferQueued"):
        normalized["socialPostsQueued"] = True
    if normalized.get("socialPostsQueued"):
        normalized["instagramQueued"] = True
    return normalized


def chapter_ledger_updates_for_folder(folder: Path, metadata: dict[str, Any], status: str = "") -> tuple[str, int, dict[str, Any]]:
    abbr = story_key(str(metadata.get("abbr") or metadata.get("novel") or ""))
    chapter_value = metadata.get("chapter") or metadata.get("chapter_number") or metadata.get("chapterNumber")
    if not abbr or chapter_value in ("", None):
        return "", 0, {}
    try:
        chapter_number = int(str(chapter_value).strip())
    except (TypeError, ValueError):
        return "", 0, {}
    updates: dict[str, Any] = {"title": str(metadata.get("title") or metadata.get("heading") or "").strip()}
    folders = {}
    if str(folder).startswith(str(OUTPUT_DIR.resolve())):
        folders["campaign"] = str(folder)
    elif str(folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
        folders["shorts"] = str(folder)
    elif str(folder).startswith(str(YOUTUBE_OUTPUT_DIR.resolve())):
        folders["youtube"] = str(folder)
    elif str(folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        folders["social"] = str(folder)
    if folders:
        updates["folders"] = folders
    if status:
        updates[status] = True
        updates[f"{status}At"] = time.strftime("%Y-%m-%d %H:%M:%S")
    updates = {key: value for key, value in updates.items() if value not in ("", None, {})}
    return abbr, chapter_number, updates


def update_chapter_ledger(abbr: str, chapter: int | str, updates: dict[str, Any]) -> dict[str, Any]:
    abbr = story_key(abbr)
    if not abbr:
        return {}
    try:
        chapter_number = int(chapter)
    except (TypeError, ValueError):
        return {}
    ledger = load_chapter_ledger()
    key = f"{abbr}-{chapter_number}"
    entry = normalize_chapter_ledger_entry(abbr, chapter_number, ledger.setdefault("chapters", {}).get(key, {}))
    existing_folders = dict(entry.get("folders") or {})
    new_folders = updates.pop("folders", {}) if isinstance(updates.get("folders"), dict) else {}
    entry.update(
        {
            "abbr": abbr,
            "novel": NOVEL_NAMES.get(abbr, abbr),
            "chapter": chapter_number,
            "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            **updates,
        }
    )
    if new_folders:
        entry["folders"] = {**existing_folders, **new_folders}
    entry = normalize_chapter_ledger_entry(abbr, chapter_number, entry)
    ledger["chapters"][key] = entry
    save_chapter_ledger(ledger)
    mirror_chapter_ledger_to_database(entry)
    return entry


def chapter_ledger_entry(abbr: str, chapter: int | str) -> dict[str, Any]:
    abbr = story_key(abbr)
    try:
        chapter_number = int(chapter)
    except (TypeError, ValueError):
        return {}
    try:
        entry = automation_db.load_chapter_ledger_entry(ROOT, abbr, chapter_number)
        if isinstance(entry, dict):
            return normalize_chapter_ledger_entry(abbr, chapter_number, entry)
    except Exception as exc:
        print(f"Database read failed for chapter ledger entry: {exc}", file=sys.stderr)
    ledger = load_chapter_ledger()
    return normalize_chapter_ledger_entry(abbr, chapter_number, ledger.get("chapters", {}).get(f"{abbr}-{chapter_number}", {}))


# --- release status (wider closure injected) ---

# release_status_for_chapter depends on release-schedule machinery not yet extracted
# (Tasks 3-4 own it). Injected as collaborators; app.py wires the real fns at Task 8.
REQUIRED_RELEASE_STATUS_COLLABORATORS = [
    "novel_schedule_entry",
    "chapter_release_dates",
    "iso_today",
    "load_release_status",
]


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"release_state: collaborator '{name}' not injected. "
            f"app.py must pass collaborators={{'{name}': <real fn>}} at Task 8."
        )
    return _fn


def _default_release_status_collaborators() -> dict[str, Any]:
    return {name: _stub_raise(name) for name in REQUIRED_RELEASE_STATUS_COLLABORATORS}


# Module-global collaborator registry (see promo_builder for the convention).
_RELEASE_STATUS_COLLAB: dict[str, Any] = _default_release_status_collaborators()


def set_release_status_collaborators(collab: dict[str, Any]) -> None:
    """Wire the real app.py functions into release_status_for_chapter. Call once at startup."""
    global _RELEASE_STATUS_COLLAB
    _RELEASE_STATUS_COLLAB = dict(collab)


def get_release_status_collaborators() -> dict[str, Any]:
    return dict(_RELEASE_STATUS_COLLAB)


def release_status_for_chapter(
    abbr: str,
    chapter: int,
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _RELEASE_STATUS_COLLAB
    abbr = abbr.upper().strip()
    novel = _get_rc(collab, "novel_schedule_entry")(abbr)
    current_rr = int(novel.get("currentRoyalRoadChapter", 0))
    dates = _get_rc(collab, "chapter_release_dates")(abbr, chapter)
    today = _get_rc(collab, "iso_today")()
    override: dict[str, Any] = {}
    try:
        db_override = automation_db.load_release_status_entry(ROOT, abbr, chapter)
        if isinstance(db_override, dict):
            override = db_override
    except Exception as exc:
        print(f"Database read failed for release status entry: {exc}", file=sys.stderr)
    if not override:
        saved_status = _get_rc(collab, "load_release_status")()
        override = saved_status.get("chapters", {}).get(f"{abbr}-{chapter}", {}) or saved_status.get("chapters", {}).get(f"{abbr.upper()}-{chapter}", {})
    if override.get("innerDiscipleDate") or override.get("pathInitiateDate") or override.get("royalRoadDate"):
        dates = {
            "innerDiscipleDate": str(override.get("innerDiscipleDate") or dates.get("innerDiscipleDate") or ""),
            "pathInitiateDate": str(override.get("pathInitiateDate") or dates.get("pathInitiateDate") or ""),
            "royalRoadDate": str(override.get("royalRoadDate") or dates.get("royalRoadDate") or ""),
        }
    rr_exists = bool(override.get("royalRoadExists")) or chapter <= current_rr
    rr_chapter_url = str(override.get("royalRoadChapterUrl") or "").strip()
    rr_content_status = str(override.get("royalRoadContentStatus") or "").strip()
    rr_content_compare = override.get("royalRoadContentCompare") if isinstance(override.get("royalRoadContentCompare"), dict) else {}
    patreon_exists = bool(override.get("patreonExists"))
    patreon_due = bool(dates.get("innerDiscipleDate")) and today >= datetime.fromisoformat(dates["innerDiscipleDate"]).date()
    rr_due = bool(dates.get("royalRoadDate")) and today >= datetime.fromisoformat(dates["royalRoadDate"]).date()
    return {
        "abbr": abbr,
        "novel": NOVEL_NAMES.get(abbr, abbr),
        "chapter": chapter,
        "patreonExists": patreon_exists,
        "patreonDue": patreon_due and not patreon_exists,
        "royalRoadExists": rr_exists,
        "royalRoadChapterUrl": rr_chapter_url,
        "royalRoadContentStatus": rr_content_status,
        "royalRoadContentCompare": rr_content_compare,
        "royalRoadDue": rr_due and not rr_exists,
        "dates": dates,
        "source": "manual override + schedule" if override else "schedule",
    }


def _get_rc(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn
