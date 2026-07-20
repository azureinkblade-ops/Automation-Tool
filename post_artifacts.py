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
