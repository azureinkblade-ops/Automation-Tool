"""Daily-social manifest I/O for the weekday cadence.

A day's folder is self-contained: manifest.json, a human-readable manifest.md and
manifest.csv, and copies of every image/clip under media/. Manifest paths are
relative only. Re-running a day keeps any posted_url / posted_at Social already filled in.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tools.weekday_cadence_config import (
    MANIFEST_CSV,
    MANIFEST_JSON,
    MANIFEST_MD,
    MEDIA_SUBDIR,
    SCHEMA_VERSION,
    STATUS_AWAITING_APPROVAL,
    STATUS_AWAITING_DAVID,
    STATUS_HELD,
    STATUS_READY,
    STATUSES,
    WeekdayCadenceConfig,
)

ITEM_FIELDS = (
    "id",
    "platform",
    "novel",
    "source_chapter",
    "source_platform",
    "caption",
    "media",
    "status",
    "hold_reason",
    "posted_url",
    "posted_at",
)


class ManifestError(ValueError):
    """Raised when a manifest or media path is invalid."""


@dataclass
class CadenceItem:
    id: str
    platform: str
    novel: str
    source_chapter: int | None
    source_platform: str
    caption: str = ""
    media: list[str] = field(default_factory=list)
    status: str = STATUS_HELD
    hold_reason: str | None = None
    posted_url: str = ""
    posted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "novel": self.novel,
            "source_chapter": self.source_chapter,
            "source_platform": self.source_platform,
            "caption": self.caption,
            "media": list(self.media),
            "status": self.status,
            "hold_reason": self.hold_reason,
            "posted_url": self.posted_url,
            "posted_at": self.posted_at,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CadenceItem":
        media = raw.get("media") or []
        if isinstance(media, str):
            media = [media]
        chapter = raw.get("source_chapter")
        if chapter in ("", None):
            chapter_value: int | None = None
        else:
            chapter_value = int(chapter)
        return cls(
            id=str(raw.get("id") or "").strip(),
            platform=str(raw.get("platform") or "").strip().lower(),
            novel=str(raw.get("novel") or "").strip().upper(),
            source_chapter=chapter_value,
            source_platform=str(raw.get("source_platform") or "").strip().lower(),
            caption=str(raw.get("caption") or ""),
            media=[str(name) for name in media],
            status=str(raw.get("status") or STATUS_HELD).strip(),
            hold_reason=(
                None
                if raw.get("hold_reason") in (None, "")
                else str(raw.get("hold_reason"))
            ),
            posted_url=str(raw.get("posted_url") or ""),
            posted_at=str(raw.get("posted_at") or ""),
        )


def item_id(novel: str, platform: str) -> str:
    return f"{str(novel).strip().upper()}-{str(platform).strip().lower()}"


def _is_absolute(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    path = Path(text)
    if path.is_absolute():
        return True
    if len(text) >= 2 and text[1] == ":":
        return True
    return text.startswith("/") or text.startswith("\\")


def assert_relative_media(names: Iterable[str], *, field_name: str = "media") -> list[str]:
    out: list[str] = []
    for raw in names:
        name = str(raw or "").replace("\\", "/").strip()
        if not name:
            continue
        if _is_absolute(name) or name.startswith("../") or "/../" in f"/{name}/":
            raise ManifestError(f"{field_name} must be a relative path inside the day folder, got {raw!r}")
        out.append(name)
    return out


def validate_item(item: CadenceItem | Mapping[str, Any]) -> CadenceItem:
    parsed = item if isinstance(item, CadenceItem) else CadenceItem.from_dict(item)
    if not parsed.id:
        raise ManifestError("item.id is required")
    if not parsed.platform:
        raise ManifestError(f"{parsed.id}: platform is required")
    if not parsed.novel:
        raise ManifestError(f"{parsed.id}: novel is required")
    if parsed.status not in STATUSES:
        raise ManifestError(f"{parsed.id}: invalid status {parsed.status!r}")
    parsed.media = assert_relative_media(parsed.media)
    return parsed


def rollup_status(items: Sequence[CadenceItem]) -> str:
    if not items:
        return STATUS_HELD
    statuses = {item.status for item in items}
    if statuses == {STATUS_HELD}:
        return STATUS_HELD
    if STATUS_AWAITING_APPROVAL in statuses and STATUS_READY not in statuses and STATUS_AWAITING_DAVID not in statuses:
        return "awaiting_identity_approval" if statuses <= {STATUS_AWAITING_APPROVAL, STATUS_HELD} else "partial"
    if STATUS_HELD in statuses or STATUS_AWAITING_APPROVAL in statuses:
        return "partial"
    if statuses <= {STATUS_READY, STATUS_AWAITING_DAVID}:
        return "ready"
    return "partial"


def summarize(items: Sequence[CadenceItem]) -> dict[str, int]:
    counts = {
        "expected": len(items),
        "ready": 0,
        "held": 0,
        "awaiting_approval": 0,
        "awaiting_david_post": 0,
    }
    for item in items:
        if item.status == "ready":
            counts["ready"] += 1
        elif item.status == "held":
            counts["held"] += 1
        elif item.status == "awaiting_approval":
            counts["awaiting_approval"] += 1
        elif item.status == "awaiting_david_post":
            counts["awaiting_david_post"] += 1
    return counts


def build_manifest(
    *,
    target_date: str,
    target_weekday: str,
    items: Sequence[CadenceItem | Mapping[str, Any]],
    config: WeekdayCadenceConfig,
    generated_at: str,
    approval_deadline: str,
    source_commit: str = "",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = [validate_item(item) for item in items]
    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "manifestId": f"cadence-{target_date}",
        "targetDate": target_date,
        "targetWeekday": target_weekday,
        "timezone": config.timezone,
        "generatedAt": generated_at,
        "approvalDeadline": approval_deadline,
        "sourceCommit": source_commit,
        "status": rollup_status(parsed),
        "config": config.to_dict(),
        "items": [item.to_dict() for item in parsed],
        "identity_batch": {
            "dueBy": approval_deadline,
            "item_ids": [item.id for item in parsed if item.status == "awaiting_approval"],
        },
        "summary": summarize(parsed),
    }
    if extra:
        for key, value in extra.items():
            if key not in payload:
                payload[key] = value
    return payload


def items_from_manifest(payload: Mapping[str, Any]) -> list[CadenceItem]:
    rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    return [validate_item(row) for row in rows if isinstance(row, Mapping)]


def _posted_filled(value: Any) -> bool:
    return bool(str(value or "").strip())


def merge_posted_fields(
    incoming: Sequence[CadenceItem],
    existing: Sequence[CadenceItem] | Mapping[str, Any] | None,
) -> list[CadenceItem]:
    """Keep Social-filled posted_url / posted_at when a day is rebuilt."""
    prior_items: list[CadenceItem]
    if existing is None:
        prior_items = []
    elif isinstance(existing, Mapping):
        prior_items = items_from_manifest(existing)
    else:
        prior_items = list(existing)
    previous = {item.id: item for item in prior_items}
    merged: list[CadenceItem] = []
    for item in incoming:
        old = previous.get(item.id)
        if old is not None:
            if _posted_filled(old.posted_url):
                item.posted_url = old.posted_url
            if _posted_filled(old.posted_at):
                item.posted_at = old.posted_at
        merged.append(item)
    return merged


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError("manifest.json must contain an object")
    items_from_manifest(data)
    return data


def write_json_atomic(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def write_manifest_md(path: Path, payload: Mapping[str, Any]) -> None:
    items = items_from_manifest(payload)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else summarize(items)
    lines = [
        f"# Daily social {payload.get('targetDate', '')} ({payload.get('targetWeekday', '')})",
        "",
        f"Status: {payload.get('status', '')}",
        f"Timezone: {payload.get('timezone', '')}",
        f"Approval deadline: {payload.get('approvalDeadline', '')}",
        f"Summary: ready={summary.get('ready', 0)} held={summary.get('held', 0)} "
        f"awaiting_approval={summary.get('awaiting_approval', 0)} "
        f"awaiting_david_post={summary.get('awaiting_david_post', 0)}",
        "",
        "| id | platform | novel | source_chapter | source_platform | status | hold_reason | media | caption | posted_url | posted_at |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        caption = " ".join(str(item.caption).split()).replace("|", "/")
        if len(caption) > 80:
            caption = caption[:77] + "..."
        media = ", ".join(item.media)
        hold = item.hold_reason or ""
        chapter = "" if item.source_chapter is None else str(item.source_chapter)
        lines.append(
            f"| {item.id} | {item.platform} | {item.novel} | {chapter} | {item.source_platform} | "
            f"{item.status} | {hold} | {media} | {caption} | {item.posted_url} | {item.posted_at} |"
        )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest_csv(path: Path, payload: Mapping[str, Any]) -> None:
    items = items_from_manifest(payload)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ITEM_FIELDS))
        writer.writeheader()
        for item in items:
            row = item.to_dict()
            row["media"] = ";".join(item.media)
            row["source_chapter"] = "" if item.source_chapter is None else item.source_chapter
            writer.writerow(row)


def unique_media_name(original: Path, *, novel: str, role: str, used: set[str]) -> str:
    suffix = original.suffix.lower() or ".bin"
    base = f"{str(novel).upper()}-{role}{suffix}"
    candidate = f"{MEDIA_SUBDIR}/{base}"
    if candidate not in used:
        used.add(candidate)
        return candidate
    stem = Path(base).stem
    index = 2
    while True:
        candidate = f"{MEDIA_SUBDIR}/{stem}-{index}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def copy_media_file(source: Path, day_dir: Path, relative_name: str) -> str:
    name = assert_relative_media([relative_name])[0]
    destination = Path(day_dir) / Path(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return name


def day_dir(root: Path, target_date: str, *, output_dirname: str = "daily-social") -> Path:
    return Path(root) / output_dirname / target_date


def save_day_bundle(
    day_path: Path,
    payload: Mapping[str, Any],
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    day_path = Path(day_path)
    day_path.mkdir(parents=True, exist_ok=True)
    items = merge_posted_fields(items_from_manifest(payload), existing)
    merged = dict(payload)
    merged["items"] = [item.to_dict() for item in items]
    merged["summary"] = summarize(items)
    merged["status"] = rollup_status(items)
    write_json_atomic(day_path / MANIFEST_JSON, merged)
    write_manifest_md(day_path / MANIFEST_MD, merged)
    write_manifest_csv(day_path / MANIFEST_CSV, merged)
    return merged
