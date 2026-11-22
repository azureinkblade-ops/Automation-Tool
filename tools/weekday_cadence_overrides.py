"""Verified-live Patreon overrides for the weekday chapter picker.

A teammate who confirmed a chapter on the real Patreon page can list it here.
A complete override entry beats the ledger's not-posted / missing flag for that
chapter. Without an override, local release-status records (patreonExists) stay
the source. Incomplete entries are ignored. This module never calls the Patreon API.

The shipped file is empty on purpose. Do not invent entries. Known context that
must wait for Product Performance's check before anything is added: EN-140 is
reported live as Patreon post 173664094, and HA-94 through HA-99 jobs were
cancelled as already live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_OVERRIDE_RELATIVE = "daily-social/patreon_live_overrides.json"
OVERRIDE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PatreonLiveOverride:
    abbr: str
    chapter: int
    post_url: str
    verified_at: str
    verified_by: str
    chapter_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "abbr": self.abbr,
            "chapter": self.chapter,
            "post_url": self.post_url,
            "verified_at": self.verified_at,
            "verified_by": self.verified_by,
        }


def empty_override_document() -> dict[str, Any]:
    return {
        "schemaVersion": OVERRIDE_SCHEMA_VERSION,
        "notes": (
            "Teammate-confirmed live Patreon chapters. A complete entry "
            "(chapter id, post_url, verified_at, verified_by) beats the ledger's "
            "not-posted flag. Without an entry, the ledger stays the source. "
            "Leave entries empty until Product Performance verifies. Do not invent "
            "rows. Reported but not added: EN-140 as Patreon post 173664094; "
            "HA-94 through HA-99 cancelled as already live, awaiting that check."
        ),
        "entries": [],
    }


def _parse_chapter_id(raw: Mapping[str, Any]) -> tuple[str, int] | None:
    abbr = str(raw.get("abbr") or "").strip().upper()
    chapter = raw.get("chapter")
    chapter_id = str(raw.get("chapter_id") or raw.get("id") or "").strip().upper().replace("_", "-")
    if abbr and chapter not in (None, ""):
        try:
            number = int(chapter)
        except (TypeError, ValueError):
            return None
        if number > 0:
            return abbr, number
    if "-" in chapter_id:
        left, right = chapter_id.rsplit("-", 1)
        if left and right.isdigit() and int(right) > 0:
            return left, int(right)
    return None


def parse_override_entry(raw: Mapping[str, Any] | None) -> PatreonLiveOverride | None:
    """Return a complete override, or None if any required field is missing."""
    if not isinstance(raw, Mapping):
        return None
    parsed = _parse_chapter_id(raw)
    if parsed is None:
        return None
    abbr, chapter = parsed
    post_url = str(raw.get("post_url") or raw.get("url") or "").strip()
    verified_at = str(raw.get("verified_at") or "").strip()
    verified_by = str(raw.get("verified_by") or "").strip()
    if not post_url or not verified_at or not verified_by:
        return None
    return PatreonLiveOverride(
        abbr=abbr,
        chapter=chapter,
        post_url=post_url,
        verified_at=verified_at,
        verified_by=verified_by,
        chapter_id=f"{abbr}-{chapter}",
    )


def load_patreon_live_overrides(path: Path | None) -> list[PatreonLiveOverride]:
    if path is None:
        return []
    file_path = Path(path)
    if not file_path.is_file():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return []
    out: list[PatreonLiveOverride] = []
    seen: set[str] = set()
    for row in rows:
        entry = parse_override_entry(row if isinstance(row, Mapping) else None)
        if entry is None or entry.chapter_id in seen:
            continue
        seen.add(entry.chapter_id)
        out.append(entry)
    return out


def overrides_for_novel(entries: Sequence[PatreonLiveOverride], novel: str) -> list[PatreonLiveOverride]:
    abbr = str(novel).strip().upper()
    return [entry for entry in entries if entry.abbr == abbr]


def write_empty_override_file(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(empty_override_document(), indent=2) + "\n", encoding="utf-8")
    return path
