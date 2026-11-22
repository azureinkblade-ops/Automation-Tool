"""Verified-live Patreon overrides for the weekday chapter picker.

A teammate who confirmed a chapter on the real Patreon page can list it here.
A complete override entry beats the ledger's not-posted / missing flag for that
chapter. Without an override, chapter_ledger postedToPatreon plus post records
stay the source. Incomplete entries are ignored. This module never calls the
Patreon API and never writes to the ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_OVERRIDE_RELATIVE = "daily-social/patreon_live_overrides.json"
OVERRIDE_SCHEMA_VERSION = 1
PATREON_POST_URL = "https://www.patreon.com/posts/{id}"


def patreon_post_url(post_id: str) -> str:
    return PATREON_POST_URL.format(id=str(post_id).strip())


@dataclass(frozen=True)
class PatreonPostRef:
    post_id: str
    tier: str | None = None
    post_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {"id": self.post_id, "post_url": self.post_url or patreon_post_url(self.post_id)}
        if self.tier:
            payload["tier"] = self.tier
        return payload


@dataclass(frozen=True)
class PatreonLiveOverride:
    abbr: str
    chapter: int
    post_url: str
    verified_at: str
    verified_by: str
    chapter_id: str
    post_ids: tuple[PatreonPostRef, ...] = ()
    tiers_live: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "chapter_id": self.chapter_id,
            "abbr": self.abbr,
            "chapter": self.chapter,
            "post_url": self.post_url,
            "verified_at": self.verified_at,
            "verified_by": self.verified_by,
        }
        if self.post_ids:
            payload["post_ids"] = [item.to_dict() for item in self.post_ids]
        if self.tiers_live:
            payload["tiers_live"] = list(self.tiers_live)
        return payload


def empty_override_document() -> dict[str, Any]:
    return {
        "schemaVersion": OVERRIDE_SCHEMA_VERSION,
        "notes": (
            "Teammate-confirmed live Patreon chapters. A complete entry "
            "(chapter id, post URL or post IDs, verified_at, verified_by) beats "
            "the ledger's not-posted flag. Without an entry, chapter_ledger "
            "postedToPatreon plus post records stay the source. Leave entries "
            "empty only when nothing has been confirmed. Do not invent rows "
            "and do not edit the chapter ledger from this file."
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


def _parse_post_refs(raw: Mapping[str, Any]) -> list[PatreonPostRef]:
    refs: list[PatreonPostRef] = []
    seen: set[str] = set()
    rows = raw.get("post_ids") or raw.get("posts") or []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                post_id = str(row.get("id") or row.get("post_id") or "").strip()
                tier = str(row.get("tier") or "").strip() or None
                url = str(row.get("post_url") or row.get("url") or "").strip()
            else:
                post_id = str(row or "").strip()
                tier = None
                url = ""
            if not post_id or post_id in seen:
                continue
            seen.add(post_id)
            refs.append(PatreonPostRef(post_id=post_id, tier=tier, post_url=url or patreon_post_url(post_id)))
    # Also accept a bare post_url / post_id on the entry itself.
    bare_url = str(raw.get("post_url") or raw.get("url") or "").strip()
    bare_id = str(raw.get("post_id") or "").strip()
    if bare_url and "/posts/" in bare_url:
        bare_id = bare_id or bare_url.rstrip("/").rsplit("/", 1)[-1]
    if bare_id and bare_id not in seen:
        refs.append(PatreonPostRef(post_id=bare_id, post_url=bare_url or patreon_post_url(bare_id)))
    return refs


def _parse_tiers(raw: Mapping[str, Any], refs: Sequence[PatreonPostRef]) -> tuple[str, ...]:
    declared = raw.get("tiers_live") or raw.get("live_tiers") or []
    names: list[str] = []
    if isinstance(declared, (list, tuple)):
        for item in declared:
            name = str(item or "").strip()
            if name and name not in names:
                names.append(name)
    for ref in refs:
        if ref.tier and ref.tier not in names:
            names.append(ref.tier)
    return tuple(names)


def parse_override_entry(raw: Mapping[str, Any] | None) -> PatreonLiveOverride | None:
    """Return a complete override, or None if any required field is missing."""
    if not isinstance(raw, Mapping):
        return None
    parsed = _parse_chapter_id(raw)
    if parsed is None:
        return None
    abbr, chapter = parsed
    refs = _parse_post_refs(raw)
    post_url = str(raw.get("post_url") or raw.get("url") or "").strip()
    if not post_url and refs:
        post_url = refs[0].post_url
    verified_at = str(raw.get("verified_at") or "").strip()
    verified_by = str(raw.get("verified_by") or "").strip()
    if (not post_url and not refs) or not verified_at or not verified_by:
        return None
    return PatreonLiveOverride(
        abbr=abbr,
        chapter=chapter,
        post_url=post_url,
        verified_at=verified_at,
        verified_by=verified_by,
        chapter_id=f"{abbr}-{chapter}",
        post_ids=tuple(refs),
        tiers_live=_parse_tiers(raw, refs),
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


def override_for_chapter(
    entries: Sequence[PatreonLiveOverride], novel: str, chapter: int | None
) -> PatreonLiveOverride | None:
    if chapter is None:
        return None
    abbr = str(novel).strip().upper()
    for entry in entries:
        if entry.abbr == abbr and entry.chapter == int(chapter):
            return entry
    return None


def write_empty_override_file(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(empty_override_document(), indent=2) + "\n", encoding="utf-8")
    return path
