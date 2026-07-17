"""X / Facebook browser-assisted publishing (Task 6 of the extraction).

Extracts the manual publish-assist surface: publish_x_post (X/Twitter media upload + tweet)
and manual_facebook_assist (quality gate + clipboard + browser handoff).

Both fns reach external network / OS browser launchers. Per the plan's injection pattern
those are supplied through COLLABORATORS with safe stubs by default; app.py wires the real
functions at Task 8. The pure folder/metadata reads use promo_copy helpers; the SOCIAL/
EXPERIMENT output dirs come from config.

Imports ONLY app_config (constants), app_state, promo_copy (read_json_safe + story_key),
release_state (ledger writes). MUST NOT import app.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 6).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state  # noqa: F401 (reserved for future in-module locks/caches)
import promo_copy as copy
import release_state as rs

# Re-exported config constants used below.
ROOT = config.ROOT
SOCIAL_OUTPUT_DIR = config.SOCIAL_OUTPUT_DIR
EXPERIMENT_OUTPUT_DIR = config.EXPERIMENT_OUTPUT_DIR

# promo_copy provides the pure helpers.
read_json_safe = copy.read_json_safe
story_key = copy.story_key

# release_state provides the ledger writes.
chapter_ledger_updates_for_folder = rs.chapter_ledger_updates_for_folder
update_chapter_ledger = rs.update_chapter_ledger


# --- not-yet-extracted collaborators (stubs; wired by app.py at Task 8) ---

REQUIRED_COLLABORATORS = [
    "multipart_bearer_request",
    "bearer_json_request",
    "ensure_quality_gate",
    "browser_launcher",
    "open_url_once",
    "clipboard_copy",
    "record_recovery_event",
    "chapter_ledger_updates_for_folder",
    "update_chapter_ledger",
    "advance_completed_chapter",
    "chapter_can_advance_active_path",
]


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"browser_publish: collaborator '{name}' not injected. "
            f"app.py must pass collaborators={{'{name}': <real fn>}} at Task 8."
        )
    return _fn


def _default_collaborators() -> dict[str, Any]:
    return {name: _stub_raise(name) for name in REQUIRED_COLLABORATORS}


def _get(collab: dict[str, Any], name: str):
    fn = collab.get(name)
    if fn is None:
        fn = _stub_raise(name)
    return fn


# --- publish_x_post (verbatim; network collaborators injected) ---

def publish_x_post(folder: str, *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
    token = os.environ.get("X_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("X is not configured. Add X_ACCESS_TOKEN to .env.local or save it in Connections.")
    post_folder = Path(folder).resolve()
    if not str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())):
        raise RuntimeError("Social post folder is not valid.")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"]).resolve()

    upload = _get(collab, "multipart_bearer_request")(
        "https://api.x.com/2/media/upload",
        token,
        {"media_category": "tweet_image"},
        {"media": image_path},
    )
    media_id = upload.get("data", {}).get("id") or upload.get("media_id_string") or upload.get("media_id")
    if not media_id:
        raise RuntimeError(f"X media upload did not return a media id: {upload}")
    created = _get(collab, "bearer_json_request")(
        "https://api.x.com/2/tweets",
        token,
        {"text": metadata.get("x", ""), "media": {"media_ids": [str(media_id)]}},
    )
    metadata["x_publish"] = {
        "media_upload": upload,
        "post_response": created,
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"media_id": media_id, "post_response": created}


# --- manual_facebook_assist (verbatim; browser launcher + clipboard injected) ---

def manual_facebook_assist(folder: str, *, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    collab = collaborators or _default_collaborators()
    post_folder = Path(folder).resolve()
    if not (
        str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve()))
        or str(post_folder).startswith(str(EXPERIMENT_OUTPUT_DIR.resolve()))
    ):
        raise RuntimeError("Social post folder is not valid.")
    _get(collab, "ensure_quality_gate")(str(post_folder), "facebook")
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain social post metadata.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    image_path = Path(metadata["image"]).resolve()
    facebook_file = post_folder / "facebook.txt"
    if not facebook_file.exists():
        facebook_file.write_text(str(metadata.get("facebook", "")).strip() + "\n", encoding="utf-8")
    try:
        _get(collab, "clipboard_copy")(facebook_file)
    except Exception:
        pass
    try:
        _get(collab, "browser_launcher")(str(post_folder))
    except Exception:
        pass
    try:
        _get(collab, "open_url_once")("https://www.facebook.com/")
    except Exception:
        pass
    metadata["manual_facebook_assist"] = {
        "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image": str(image_path),
        "facebook_file": str(facebook_file),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "image": str(image_path),
        "text": metadata.get("facebook", ""),
        "facebook_file": str(facebook_file),
        "folder": str(post_folder),
        "message": "Opened Facebook and the post folder. Facebook text copied to clipboard.",
    }
