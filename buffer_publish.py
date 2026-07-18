"""Buffer API + channel routing (Task 6 of the extraction).

Extracts the Buffer publish surface: buffer_graphql (the Buffer GraphQL request fn),
configured_buffer_channels, buffer_channel_service, and buffer_post_from_folder
(the pack->Buffer routing/queue fn).

buffer_post_from_folder is the widest routing fn in the codebase; it calls many
not-yet-extracted helpers. Per the plan's injection pattern those are supplied through
COLLABORATORS with safe stubs by default; app.py wires the real functions at Task 8.
The Buffer network boundary (create_buffer_post -> buffer_graphql) and the pure
channel-routing fns (configured_buffer_channels, buffer_channel_service) are local.

Imports ONLY app_config (constants), app_state, release_state (ledger + atomic JSON),
promo_copy (read_json_safe + story_key), and any module-level pure helpers that have
already been extracted. MUST NOT import app.

Behavior preserved verbatim from app.py. See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 6).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import app_config as config
import app_state as state  # noqa: F401 (reserved for future in-module locks/caches)
import promo_copy as copy
import release_state as rs

# Re-exported config constants used below.
ROOT = config.ROOT
SOCIAL_OUTPUT_DIR = config.SOCIAL_OUTPUT_DIR
TIKTOK_OUTPUT_DIR = config.TIKTOK_OUTPUT_DIR
YOUTUBE_OUTPUT_DIR = config.YOUTUBE_OUTPUT_DIR
OUTPUT_DIR = config.OUTPUT_DIR
EXPERIMENT_OUTPUT_DIR = config.EXPERIMENT_OUTPUT_DIR
VIDEO_EXTENSIONS = config.VIDEO_EXTENSIONS

# release_state provides the ledger writes.
chapter_ledger_updates_for_folder = rs.chapter_ledger_updates_for_folder
update_chapter_ledger = rs.update_chapter_ledger

# promo_copy provides the pure helpers.
read_json_safe = copy.read_json_safe
story_key = copy.story_key


# --- not-yet-extracted collaborators (stubs; wired by app.py at Task 8) ---

REQUIRED_COLLABORATORS = [
    "read_metadata",
    "normalize_chapter_id",
    "stable_chapter_folder",
    "repair_deep_tiktok_metadata",
    "ensure_buffer_video",
    "folder_quality_gate",
    "record_recovery_event",
    "github_auto_publish_media",
    "publish_folder_media_to_github",
    "create_buffer_post",
    "buffer_queue_full_error",
    "buffer_queue_full_fallback",
    "video_meets_minimum_duration",
    "media_duration_seconds",
    "post_record_from_folder",
    "save_post_record",
    "update_clickup_on_publish",
    "clickup_configured",
    "post_progress_tool",
    "advance_completed_chapter",
    "chapter_can_advance_active_path",
    "cleanup_generated_folder",
]


def _stub_raise(name: str):
    def _fn(*args, **kwargs):
        raise NotImplementedError(
            f"buffer_publish: collaborator '{name}' not injected. "
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


# --- local, self-contained Buffer request fn (the network boundary) ---

def buffer_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Buffer is not configured. Add BUFFER_API_KEY in Connections.")
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.buffer.com",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Buffer API failed: HTTP {exc.code} {detail}") from exc
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload


# --- local channel routing (pure, self-contained) ---

def configured_buffer_channels() -> list[dict[str, str]]:
    ids = [value.strip() for value in os.environ.get("BUFFER_CHANNEL_IDS", "").split(",") if value.strip()]
    labels = [("instagram", "Instagram"), ("tiktok", "TikTok"), ("youtube", "YouTube")]
    channels: list[dict[str, str]] = []
    for index, channel_id in enumerate(ids):
        service, name = labels[index] if index < len(labels) else ("buffer", f"Buffer Channel {index + 1}")
        raw_id = channel_id
        if ":" in channel_id:
            prefix, raw_id = channel_id.split(":", 1)
            prefix = prefix.strip().lower()
            if prefix in {"instagram", "tiktok", "youtube"}:
                service = prefix
                name = prefix.title()
        channels.append({"id": raw_id.strip(), "service": service, "name": name, "source": "saved"})
    return channels


def buffer_channel_service(channel_id: str) -> str:
    for channel in configured_buffer_channels():
        if channel.get("id") == channel_id:
            return channel.get("service", "buffer")
    return "buffer"


# --- buffer_post_from_folder (verbatim routing fn; collaborators injected) ---

def buffer_post_from_folder(
    folder: str,
    channel_ids: list[str],
    text_kind: str,
    mode: str = "addToQueue",
    scheduled_at: str | None = None,
    advance_path: bool = True,
    *,
    collaborators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collab = collaborators if collaborators is not None else _COLLAB
    if mode not in {"addToQueue", "draft"}:
        raise RuntimeError("Buffer mode must be addToQueue or draft.")
    post_folder = Path(folder).resolve()
    if str(post_folder).startswith(str(YOUTUBE_OUTPUT_DIR.resolve())):
        metadata_probe = _get(collab, "read_metadata")(post_folder)
        probe_title = str(metadata_probe.get("title") or post_folder.name)
        probe_abbr = str(metadata_probe.get("abbr") or "")
        probe_chapter = _get(collab, "normalize_chapter_id")(probe_title, metadata_probe.get("chapter") or "")
        if not probe_abbr:
            name_match = __import__("re").match(r"^(?P<abbr>[a-z]{2})-(?:(?P<chapter>\d+[a-z]?)|chapter)-(?P<title>.+)$", post_folder.name, __import__("re").IGNORECASE)
            if name_match:
                probe_abbr = name_match.group("abbr").upper()
                probe_title = name_match.group("title")
                probe_chapter = _get(collab, "normalize_chapter_id")(probe_title, name_match.group("chapter") or "")
        stable = _get(collab, "stable_chapter_folder")(
            YOUTUBE_OUTPUT_DIR,
            "youtube",
            probe_title,
            probe_abbr,
            probe_chapter,
        ).resolve()
        if stable != post_folder and stable.exists() and ((stable / "youtube-buffer.mp4").exists() or (stable / "youtube-video.mp4").exists()):
            post_folder = stable
    metadata_path = post_folder / "metadata.json"
    if not metadata_path.exists():
        raise RuntimeError("This folder does not contain metadata.")
    metadata = _get(collab, "read_metadata")(post_folder)
    if str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())) and (
        str(metadata.get("kind") or "") == "deep_tiktok" or post_folder.name.lower().endswith("-deep")
    ):
        metadata = _get(collab, "repair_deep_tiktok_metadata")(post_folder, metadata)
    video_build = _get(collab, "ensure_buffer_video")(post_folder, text_kind)
    if video_build:
        metadata.setdefault("buffer_video_builds", []).append(video_build)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    quality = _get(collab, "folder_quality_gate")(str(post_folder), text_kind)
    if not quality.get("ok"):
        _get(collab, "record_recovery_event")(
            "buffer_quality_gate",
            "; ".join(quality.get("errors", [])) or "Quality gate failed.",
            error_type="quality_gate_failed",
            folder=post_folder,
            details=quality,
        )
        return {"posts": [], "qualityGate": quality, "skipped": True, "message": "Quality gate failed. Fix the listed issues before sending to Buffer."}
    if _get(collab, "github_auto_publish_media")():
        publish_result = _get(collab, "publish_folder_media_to_github")(str(post_folder))
        metadata.setdefault("buffer_media_publishes", []).append(publish_result)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    posts = []
    for channel_id in channel_ids:
        service = buffer_channel_service(channel_id)
        post_metadata: dict[str, Any] = {}
        if str(post_folder).startswith(str(SOCIAL_OUTPUT_DIR.resolve())) or (
            str(post_folder).startswith(str(EXPERIMENT_OUTPUT_DIR.resolve())) and metadata.get("kind") == "experiment_social_pack"
        ):
            if service != "instagram":
                posts.append({"skipped": True, "channelId": channel_id, "reason": "Daily image posts only go to Instagram."})
                continue
            text = metadata.get("instagram" if text_kind == "instagram" else "x", "")
            media = [metadata.get("image", "")]
            post_metadata = {"instagram": {"type": "post", "shouldShareToFeed": True}}
        elif str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
            video = post_folder / "tiktok-video.mp4"
            media = [str(video)] if video.exists() else metadata.get("images", [])
            if str(metadata.get("kind") or "") == "deep_tiktok" and service != "tiktok":
                posts.append({"skipped": True, "channelId": channel_id, "reason": "Deep chapter videos only go to TikTok."})
                continue
            if service == "youtube":
                text = metadata.get("youtube_shorts_description") or metadata.get("caption", "")
                post_metadata = {
                    "youtube": {
                        "title": metadata.get("youtube_shorts_title") or f"{metadata.get('novel', 'Chapter')} #{metadata.get('chapter', '')} #Shorts",
                        "categoryId": "22",
                        "license": "youtube",
                        "privacy": "private",
                        "notifySubscribers": False,
                        "embeddable": True,
                        "madeForKids": False,
                    }
                }
            elif service == "instagram":
                text = metadata.get("instagram_reel_caption") or metadata.get("caption", "")
                post_metadata = {"instagram": {"type": "reel", "shouldShareToFeed": True}}
            else:
                text = metadata.get("caption", "")
        elif str(post_folder).startswith(str(YOUTUBE_OUTPUT_DIR.resolve())):
            if service == "youtube":
                posts.append({"skipped": True, "channelId": channel_id, "reason": "Full YouTube videos are review-only in Buffer. Use the TikTok / Reel / YouTube Short pack to upload Shorts."})
                continue
            if service != "youtube":
                posts.append({"skipped": True, "channelId": channel_id, "reason": "YouTube videos only go to YouTube."})
                continue
            text = metadata.get("description", "")
            video = post_folder / "youtube-buffer.mp4"
            if not video.exists():
                video = post_folder / "youtube-video.mp4"
            media = [str(video)] if video.exists() else []
            post_metadata = (
                {
                    "youtube": {
                        "title": metadata.get("title") or "Chapter video",
                        "categoryId": "22",
                        "license": "youtube",
                        "privacy": "private",
                        "notifySubscribers": False,
                        "embeddable": True,
                        "madeForKids": False,
                    }
                }
                if service == "youtube"
                else {}
            )
        else:
            caption = metadata.get("caption") or metadata.get("patreon_note") or metadata.get("royal_road_note") or ""
            promo_video = post_folder / "promo-video.mp4"
            youtube_video = post_folder / "youtube-video.mp4"
            youtube_buffer_video = post_folder / "youtube-buffer.mp4"
            if service == "youtube":
                posts.append({"skipped": True, "channelId": channel_id, "reason": "Full YouTube videos are review-only in Buffer. Use the TikTok / Reel / YouTube Short pack to upload Shorts."})
                continue
            else:
                text = caption
                media = [str(promo_video)] if promo_video.exists() else metadata.get("images", [])
                if service == "instagram" and promo_video.exists():
                    post_metadata = {"instagram": {"type": "reel", "shouldShareToFeed": True}}
        if service == "youtube" and not media:
            posts.append({
                "skipped": True,
                "channelId": channel_id,
                "reason": "No YouTube video or Shorts video was available.",
                "videoBuild": video_build,
            })
            continue
        if service == "instagram" and post_metadata.get("instagram", {}).get("type") == "reel":
            video_media = next((Path(str(item)) for item in media if str(item).lower().endswith(tuple(VIDEO_EXTENSIONS))), None)
            if video_media and not _get(collab, "video_meets_minimum_duration")(video_media, 3.0):
                posts.append({
                    "skipped": True,
                    "channelId": channel_id,
                    "reason": f"Instagram Reels need video of at least 3 seconds. This file is {_get(collab, 'media_duration_seconds')(video_media):.2f} seconds; rebuild the short and retry.",
                    "media": str(video_media),
                    "videoBuild": video_build,
                })
                continue
        try:
            created_post = _get(collab, "create_buffer_post")(channel_id, text, [m for m in media if m], mode=mode, metadata=post_metadata, scheduled_at=scheduled_at)
            created_post["_automation"] = {"service": service, "channelId": channel_id}
            posts.append(created_post)
        except Exception as exc:
            if _get(collab, "buffer_queue_full_error")(exc):
                posts.append(
                    _get(collab, "buffer_queue_full_fallback")(
                        post_folder,
                        {
                            "service": service,
                            "channelId": channel_id,
                            "text": text,
                            "media": [m for m in media if m],
                            "metadata": post_metadata,
                        },
                        exc,
                    )
                )
            else:
                raise
    metadata.setdefault("buffer_posts", []).append({"posted_at": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "scheduled_at": scheduled_at, "responses": posts})
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    successful_posts = [post for post in posts if post and not post.get("skipped")]
    if successful_posts:
        for post in successful_posts:
            try:
                automation = post.get("_automation") if isinstance(post.get("_automation"), dict) else {}
                service = str(automation.get("service") or "buffer").lower()
                buffer_id = (
                    post.get("id")
                    or post.get("post_id")
                    or (post.get("post") if isinstance(post.get("post"), dict) else {}).get("id")
                    or (post.get("data") if isinstance(post.get("data"), dict) else {}).get("id")
                    or ""
                )
                record = _get(collab, "post_record_from_folder")(
                    post_folder,
                    service,
                    metadata,
                    bufferPostId=buffer_id,
                    publishDate=(scheduled_at[:10] if scheduled_at else time.strftime("%Y-%m-%d")),
                    publishedAt=time.strftime("%Y-%m-%d %H:%M:%S"),
                    bufferMode=mode,
                    bufferChannelId=automation.get("channelId", ""),
                )
                saved_record = _get(collab, "save_post_record")(record)
                if _get(collab, "clickup_configured")():
                    _get(collab, "update_clickup_on_publish")(saved_record)
            except Exception as exc:
                _get(collab, "record_recovery_event")(
                    "clickup_publish_sync",
                    f"ClickUp publish sync failed after Buffer success: {exc}",
                    error_type="clickup_publish_sync_failed",
                    folder=post_folder,
                    details={"post": post},
                )
        abbr, chapter_number, updates = chapter_ledger_updates_for_folder(post_folder, metadata, "socialPostsQueued")
        if abbr and chapter_number:
            queued_at = time.strftime("%Y-%m-%d %H:%M:%S")
            progress_tool = _get(collab, "post_progress_tool")(metadata)
            if progress_tool == "promo":
                updates.update(
                    {
                        "bufferQueued": True,
                        "bufferQueuedAt": queued_at,
                        "socialPostsQueuedAt": queued_at,
                    }
                )
                if str(post_folder).startswith(str(TIKTOK_OUTPUT_DIR.resolve())):
                    updates["shortsReelsQueued"] = True
                else:
                    updates["socialPostsQueuedAt"] = queued_at
            update_chapter_ledger(abbr, chapter_number, updates)
            if advance_path and _get(collab, "chapter_can_advance_active_path")(abbr, chapter_number):
                _get(collab, "advance_completed_chapter")(abbr, chapter_number, progress_tool)
    cleanup = _get(collab, "cleanup_generated_folder")(post_folder) if successful_posts else {"removed": [], "errors": []}
    return {"posts": posts, "cleanup": cleanup}
