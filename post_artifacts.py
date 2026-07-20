"""Post artifact helpers (2026-07-20 plan §2 / §4).

Owns artifact paths, manifest (metadata.json) updates, and URL generation for
post media. Kept separate from tts_service (which synthesizes) and promo_copy
(which generates text). No provider/network logic here.

Migrations: post payloads that gain audio/overlay structures carry
``artifact_schema_version`` so older campaign folders (without those fields)
continue to load.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ARTIFACT_SCHEMA_VERSION = 2


def post_audio_relative_path(content_hash: str) -> str:
    """Relative path (from the post folder) for a cached voiceover file."""
    return f".tts_cache/{content_hash}.mp3"


def post_audio_url(folder: "str | Path", content_hash: str) -> str:
    """HTTP URL the dashboard <audio> widget uses to stream the voiceover.

    The cached file lives on local disk, so we route through the app's
    /api/post-audio endpoint (a browser cannot play a file:// URL served from
    an http:// origin). Resolves symlinks and enforces that the file stays
    within the post folder; if it does not, returns an empty string so the UI
    shows no player rather than a broken/unsafe link.
    """
    path = _resolve_audio_path(folder, content_hash)
    if path is None:
        return ""
    from urllib.parse import quote
    return (
        "/api/post-audio?folder="
        + quote(str(Path(folder)), safe="")
        + "&hash="
        + quote(content_hash, safe="")
    )


def _resolve_audio_path(folder: "str | Path", content_hash: str) -> "Path | None":
    """Resolve the cached mp3 for a post, enforcing it stays under folder/.tts_cache.

    Returns the resolved Path or None when the path is unsafe / missing.
    """
    if not content_hash or "/" in content_hash or "\\" in content_hash:
        return None
    folder = Path(folder)
    candidate = (folder / ".tts_cache" / f"{content_hash}.mp3").resolve()
    # Confine to the post folder (prevents path traversal via folder param).
    try:
        candidate.relative_to(folder.resolve())
    except Exception:
        return None
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def post_audio_serve(folder: "str | Path", content_hash: str) -> "tuple[bytes, str] | None":
    """Read the cached voiceover bytes for an HTTP response.

    Returns (data, mime) or None when missing/unsafe. Caller handles the 404.
    """
    path = _resolve_audio_path(folder, content_hash)
    if path is None:
        return None
    try:
        return path.read_bytes(), "audio/mpeg"
    except Exception:
        return None


def apply_artifact_schema_version(metadata: dict[str, Any]) -> dict[str, Any]:
    """Stamp the schema version onto a post metadata dict if absent."""
    if "artifact_schema_version" not in metadata:
        metadata["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
    return metadata


def attach_audio_status(metadata: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    """Merge a tts_service status dict into the post metadata under ``audio``.

    Stores the structured payload (status/path/url/engine/voice/duration/
    cache_hit/content_hash/error) so the UI can distinguish ready / generating
    / skipped / failed without re-deriving anything.
    """
    metadata["audio"] = {
        "status": status.get("status", "failed"),
        "path": status.get("path", ""),
        "url": status.get("url", ""),
        "engine": status.get("engine", ""),
        "voice_id": status.get("voice_id", ""),
        "duration_seconds": status.get("duration_seconds", 0.0),
        "cache_hit": status.get("cache_hit", False),
        "content_hash": status.get("content_hash", ""),
        "error": status.get("error"),
    }
    return apply_artifact_schema_version(metadata)


def write_metadata(folder: "str | Path", metadata: dict[str, Any]) -> Path:
    """Atomically write metadata.json for a post folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "metadata.json.tmp"
    tmp.write_text(json.dumps(apply_artifact_schema_version(metadata), indent=2), encoding="utf-8")
    tmp.replace(folder / "metadata.json")
    return folder / "metadata.json"


def read_metadata(folder: "str | Path") -> dict[str, Any]:
    """Read metadata.json; returns {} if missing (backward compatible)."""
    path = Path(folder) / "metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
