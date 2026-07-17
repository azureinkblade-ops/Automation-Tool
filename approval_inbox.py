"""Approval inbox aggregation + clearing (Task 4 of the extraction).

Extracts the #4 review-surface aggregator: approval_inbox(), the approval-cleared
state load/save, the clear/gating helpers (filter_uncleared_approval_items,
approval_item_key/is_cleared, clear_* fns), and the weak-media blocking logic.

approval_inbox fans out to sibling aggregators owned by later tasks (youtube, patreon,
deep-tiktok, recovery, comment-assistant). Per the plan's injection pattern those are
supplied through a collaborators dict with safe stubs by default; app.py wires the real
functions at Task 8. The pure cross-cutting utils (content_hash, read_metadata,
PACK_DONE_STATUSES, approval_item_matches_active_chapter, active_chapter_path_next) are
also injected (not yet extracted).

Imports ONLY app_config (constants), app_state, automation_db, release_state (ledger +
atomic JSON writes + json read), and promo_copy (story_key). MUST NOT import app.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 4).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state  # noqa: F401 (reserved for future in-module locks/caches)
import automation_db
import promo_copy as copy
import release_state as rs

# Re-exported config constants used below.
ROOT = config.ROOT
NOVEL_NAMES = config.NOVEL_NAMES
APPROVAL_INBOX_CLEARED_FILE = config.APPROVAL_INBOX_CLEARED_FILE

# promo_copy provides story_key (pure).
story_key = copy.story_key

# release_state provides the ledger + atomic JSON + approval mirror.
load_chapter_ledger = rs.load_chapter_ledger
write_json_atomic = rs.write_json_atomic
mirror_approval_cleared_to_database = rs.mirror_approval_cleared_to_database
# promo_copy provides story_key + read_json_safe (pure helpers).
story_key = copy.story_key
read_json_safe = copy.read_json_safe
REQUIRED_COLLABORATORS = [
    # sibling aggregators owned by later tasks
    "comment_assistant_status",
    "youtube_created_not_uploaded",
    "pending_daily_shorts_items",
    "pending_deep_tiktok_items",
    "pending_patreon_items",
    "pending_manual_social_items",
    "unresolved_recovery_items",
    "load_youtube_comment_queue",
    # pure cross-cutting utils not yet extracted
    "content_hash",
    "read_metadata",
    "approval_item_matches_active_chapter",
    "active_chapter_path_next",
    # deeper clearing fns owned by later tasks (patreon/youtube/comment/fb/recovery)
    "find_current_approval_item",
    "mark_patreon_done_from_folder",
    "mark_manual_x_posted",
    "mark_manual_facebook_posted",
    "clear_youtube_comment_inbox_item",
    "clear_recovery_failure",
    "update_comment_status",
]

# Constants the gating logic references (small, immutable) -- injected as data collaborators
# so we don't guess; app.py passes PACK_DONE_STATUSES at Task 8 if it differs.
PACK_DONE_STATUSES = {"queued", "posted", "uploaded", "dismissed", "archived"}


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"approval_inbox: collaborator '{name}' not injected. "
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


# --- approval-cleared state (dual-store: JSON mirror + SQLite) ---

def load_approval_cleared_state() -> dict[str, Any]:
    try:
        data = automation_db.load_approval_cleared_state(ROOT)
        if isinstance(data, dict) and isinstance(data.get("items"), dict) and data["items"]:
            return data
    except Exception as exc:
        print(f"Database read failed for approval cleared state: {exc}", file=sys.stderr)
    data = read_json_safe(APPROVAL_INBOX_CLEARED_FILE)
    if not isinstance(data, dict):
        data = {"schemaVersion": 1, "items": {}}
    data.setdefault("items", {})
    return data


def save_approval_cleared_state(data: dict[str, Any]) -> None:
    data["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json_atomic(APPROVAL_INBOX_CLEARED_FILE, data)


# --- item keying + clearing ---

def approval_item_key(kind: str, item: dict[str, Any]) -> str:
    kind = str(kind or "").strip()
    stable = [
        kind,
        story_key(str(item.get("abbr") or "")),
        str(item.get("chapter") or ""),
        str(item.get("platform") or ""),
        str(item.get("commentId") or item.get("id") or ""),
        str(item.get("folder") or ""),
        str(item.get("video") or ""),
        str(item.get("watchUrl") or ""),
        str(item.get("errorType") or ""),
    ]
    return _get(_collab_ref, "content_hash")("|".join(stable))


def approval_item_is_cleared(kind: str, item: dict[str, Any], cleared_state: dict[str, Any] | None = None) -> bool:
    key = approval_item_key(kind, item)
    if cleared_state is None:
        try:
            if automation_db.is_approval_cleared(ROOT, key):
                return True
        except Exception as exc:
            print(f"Database read failed for approval item: {exc}", file=sys.stderr)
    state = cleared_state if isinstance(cleared_state, dict) else load_approval_cleared_state()
    items = state.get("items") if isinstance(state.get("items"), dict) else {}
    return key in items


def filter_uncleared_approval_items(
    kind: str,
    items: list[dict[str, Any]],
    cleared_state: dict[str, Any] | None = None,
    active_paths: dict[str, int | None] | None = None,
) -> list[dict[str, Any]]:
    state = cleared_state if isinstance(cleared_state, dict) else load_approval_cleared_state()
    result = []
    for item in items:
        if approval_item_is_cleared(kind, item, state):
            continue
        enriched = dict(item)
        folder = str(enriched.get("folder") or "").strip()
        if folder and Path(folder).exists():
            metadata = _get(_collab_ref, "read_metadata")(Path(folder))
            if metadata:
                enriched.setdefault("packId", metadata.get("packId"))
                enriched.setdefault("packType", metadata.get("packType"))
                enriched.setdefault("packStatus", metadata.get("packStatus"))
                enriched.setdefault("abbr", metadata.get("abbr"))
                enriched.setdefault("novel", metadata.get("novel"))
                enriched.setdefault("chapter", metadata.get("chapter") or metadata.get("chapter_number"))
                enriched.setdefault("title", metadata.get("title"))
                if kind == "deepTikToks" and metadata.get("packStatus") in PACK_DONE_STATUSES:
                    continue
                if kind == "youtube" and metadata.get("packStatus") in {"uploaded", "posted"}:
                    continue
                if kind == "failures" and metadata.get("packStatus") not in {"failed", "needs_video_build", "needs_image_review"}:
                    continue
        if kind not in {"comments", "messages", "youtubeComments"} and not _get(_collab_ref, "approval_item_matches_active_chapter")(enriched, active_paths):
            continue
        enriched["approvalKey"] = approval_item_key(kind, item)
        result.append(enriched)
    return result


# --- the aggregator (injects sibling aggregators) ---

def approval_inbox(*, collaborators: dict[str, Any] | None = None) -> dict[str, Any]:
    global _collab_ref
    _collab_ref = collaborators or _default_collaborators()
    cleared_state = load_approval_cleared_state()
    ledger = load_chapter_ledger()
    active_paths = {abbr: _get(_collab_ref, "active_chapter_path_next")(abbr, "approval") for abbr in NOVEL_NAMES}
    engagement_items = [
        item for item in _get(_collab_ref, "comment_assistant_status")().get("comments", [])
        if item.get("status") in {"pending", "prepared"}
    ]
    messages = filter_uncleared_approval_items("messages", [item for item in engagement_items if item.get("itemType") == "message"], cleared_state, active_paths)
    comments = filter_uncleared_approval_items("comments", [item for item in engagement_items if item.get("itemType") != "message"], cleared_state, active_paths)
    youtube = filter_uncleared_approval_items("youtube", _get(_collab_ref, "youtube_created_not_uploaded")(ledger), cleared_state, active_paths)
    daily_shorts = filter_uncleared_approval_items("dailyShorts", _get(_collab_ref, "pending_daily_shorts_items")(ledger), cleared_state, active_paths)
    deep_tiktoks = filter_uncleared_approval_items("deepTikToks", _get(_collab_ref, "pending_deep_tiktok_items")(ledger=ledger, active_paths=active_paths), cleared_state, active_paths)
    patreon = filter_uncleared_approval_items("patreon", _get(_collab_ref, "pending_patreon_items")(ledger, active_paths), cleared_state, active_paths)
    social = filter_uncleared_approval_items("manualSocial", _get(_collab_ref, "pending_manual_social_items")(active_paths), cleared_state, active_paths)
    failures = filter_uncleared_approval_items("failures", _get(_collab_ref, "unresolved_recovery_items")(ledger, active_paths), cleared_state, active_paths)
    youtube_comments = [
        item for item in _get(_collab_ref, "load_youtube_comment_queue")().get("items", [])
        if item.get("status") in {"ready", "posted", "failed", "waiting_public"}
        and (item.get("videoId") or item.get("watchUrl") or item.get("status") == "failed")
    ]
    youtube_comments = filter_uncleared_approval_items("youtubeComment", youtube_comments, cleared_state, active_paths)
    counts = {
        "comments": len(comments),
        "messages": len(messages),
        "youtube": len(youtube),
        "dailyShorts": len(daily_shorts),
        "deepTikToks": len(deep_tiktoks),
        "patreon": len(patreon),
        "manualSocial": len(social),
        "failures": len(failures),
        "youtubeComments": len(youtube_comments),
    }
    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": sum(counts.values()),
        "counts": counts,
        "comments": comments[:40],
        "messages": messages[:40],
        "youtube": youtube[:20],
        "dailyShorts": daily_shorts[:20],
        "deepTikToks": deep_tiktoks[:20],
        "patreon": patreon,
        "manualSocial": social,
        "failures": failures,
        "youtubeComments": youtube_comments[:20],
    }


# Module-level collaborator reference (set per approval_inbox call; also usable by the
# keying/clearing helpers below which need content_hash/read_metadata).
_collab_ref: dict[str, Any] = _default_collaborators()


# --- clearing functions (verbatim from app.py; deeper clearing fns injected as collaborators) ---

def clear_visible_approval_items() -> dict[str, Any]:
    inbox = approval_inbox()
    bucket_map = {
        "comments": "comments",
        "messages": "messages",
        "youtube": "youtube",
        "dailyShorts": "dailyShorts",
        "deepTikToks": "deepTikToks",
        "patreon": "patreon",
        "manualSocial": "manualSocial",
        "youtubeComments": "youtubeComment",
    }
    cleared = []
    for bucket, kind in bucket_map.items():
        for item in inbox.get(bucket, []) if isinstance(inbox.get(bucket), list) else []:
            cleared.append(mark_approval_item_cleared(kind, item, "dismissed_visible_approval_inbox"))
    return {
        "ok": True,
        "cleared": len(cleared),
        "message": f"Dismissed {len(cleared)} visible approval item(s).",
        "approvalInbox": approval_inbox(),
    }


def find_current_approval_item(kind: str, folder: str = "", platform: str = "", comment_id: str = "") -> dict[str, Any]:
    kind = str(kind or "").strip()
    folder = str(folder or "").strip()
    platform = str(platform or "").strip().lower()
    comment_id = str(comment_id or "").strip()
    candidates: list[dict[str, Any]] = []
    if kind == "comments":
        candidates = approval_inbox().get("comments", [])
    elif kind == "messages":
        candidates = approval_inbox().get("messages", [])
    elif kind == "youtube":
        candidates = approval_inbox().get("youtube", [])
    elif kind == "dailyShorts":
        candidates = approval_inbox().get("dailyShorts", [])
    elif kind == "deepTikToks":
        candidates = approval_inbox().get("deepTikToks", [])
    elif kind == "patreon":
        candidates = approval_inbox().get("patreon", [])
    elif kind == "manualSocial":
        candidates = approval_inbox().get("manualSocial", [])
    elif kind == "failures":
        candidates = approval_inbox().get("failures", [])
    elif kind == "youtubeComment":
        candidates = approval_inbox().get("youtubeComments", [])
    for item in candidates if isinstance(candidates, list) else []:
        if comment_id and str(item.get("commentId") or item.get("id") or "") == comment_id:
            return item
        if folder and str(item.get("folder") or "").strip():
            try:
                if str(Path(str(item.get("folder"))).resolve()) == str(Path(folder).resolve()):
                    if not platform or str(item.get("platform") or "").lower() == platform:
                        return item
            except Exception:
                if str(item.get("folder") or "") == folder and (not platform or str(item.get("platform") or "").lower() == platform):
                    return item
        if platform and str(item.get("platform") or "").lower() == platform and not folder and not comment_id:
            return item
    fallback: dict[str, Any] = {"folder": folder, "platform": platform, "commentId": comment_id}
    if comment_id:
        fallback["id"] = comment_id
    return fallback


def mark_approval_item_cleared(kind: str, item: dict[str, Any], reason: str = "cleared_from_approval_inbox") -> dict[str, Any]:
    state = load_approval_cleared_state()
    items = state.setdefault("items", {})
    key = approval_item_key(kind, item)
    items[key] = {
        "kind": kind,
        "clearedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
        "folder": str(item.get("folder") or ""),
        "platform": str(item.get("platform") or ""),
        "commentId": str(item.get("commentId") or item.get("id") or ""),
        "abbr": str(item.get("abbr") or ""),
        "chapter": str(item.get("chapter") or ""),
    }
    save_approval_cleared_state(state)
    mirror_approval_cleared_to_database(key, items[key])
    return {"approvalKey": key, "clearedRecord": items[key], "file": str(APPROVAL_INBOX_CLEARED_FILE)}


def clear_approval_inbox_item(kind: str, folder: str = "", platform: str = "", comment_id: str = "") -> dict[str, Any]:
    kind = str(kind or "").strip()
    platform = str(platform or "").strip().lower()
    matched_item = find_current_approval_item(kind, folder, platform, comment_id)
    clear_record: dict[str, Any] = {}
    if kind == "patreon":
        result = _get(_collab_ref, "mark_patreon_done_from_folder")(folder)
        clear_record = mark_approval_item_cleared(kind, matched_item)
        return {**result, **clear_record}
    if kind == "manualSocial":
        if platform == "x":
            result = _get(_collab_ref, "mark_manual_x_posted")(folder)
        elif platform == "facebook":
            result = _get(_collab_ref, "mark_manual_facebook_posted")(folder)
        else:
            raise RuntimeError("Unknown manual social platform.")
        clear_record = mark_approval_item_cleared(kind, matched_item)
        return {**result, **clear_record, "ok": True, "message": f"{platform.title()} item marked complete and removed from the approval inbox."}
    if kind == "youtubeComment":
        result = _get(_collab_ref, "clear_youtube_comment_inbox_item")(comment_id)
        clear_record = mark_approval_item_cleared(kind, matched_item)
        return {**result, **clear_record}
    if kind == "failures":
        result = _get(_collab_ref, "clear_recovery_failure")(str(matched_item.get("abbr") or ""), str(matched_item.get("chapter") or ""), str(folder or matched_item.get("folder") or ""))
        clear_record = mark_approval_item_cleared(kind, matched_item)
        return {**result, **clear_record}
    if kind in {"youtube", "deepTikToks", "comments", "messages"}:
        if kind in {"comments", "messages"} and comment_id:
            try:
                _get(_collab_ref, "update_comment_status")(comment_id, "dismissed")
            except Exception:
                pass
        clear_record = mark_approval_item_cleared(kind, matched_item)
        return {"ok": True, **clear_record, "message": "Approval item cleared and will not be shown again."}
    clear_record = mark_approval_item_cleared(kind, matched_item)
    return {"ok": True, **clear_record, "message": "Approval item cleared and will not be shown again."}
