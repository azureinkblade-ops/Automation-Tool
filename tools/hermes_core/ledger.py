"""Append-only local event ledger for Hermes governance events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_payload


class LedgerError(ValueError):
    """Raised when ledger entries fail validation or verification."""


@dataclass(frozen=True)
class LedgerEntry:
    sequence: int
    event_type: str
    task_id: str
    occurred_at: str
    payload: dict[str, Any]
    payload_sha256: str
    previous_entry_sha256: str | None
    entry_sha256: str


class EventLedger:
    """JSONL-backed append-only event ledger.

    The public API never edits existing entries. Verification replays the file
    and confirms sequence numbers, payload hashes, and chain hashes.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(
        self,
        event_type: str,
        task_id: str,
        payload: dict[str, Any],
        *,
        occurred_at: str | None = None,
    ) -> LedgerEntry:
        entries = self.replay()
        previous_hash = entries[-1].entry_sha256 if entries else None
        sequence = len(entries) + 1
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        payload_hash = sha256_payload(payload)
        entry_without_hash = {
            "sequence": sequence,
            "event_type": event_type,
            "task_id": task_id,
            "occurred_at": timestamp,
            "payload": payload,
            "payload_sha256": payload_hash,
            "previous_entry_sha256": previous_hash,
        }
        entry_hash = sha256_payload(entry_without_hash)
        raw_entry = {**entry_without_hash, "entry_sha256": entry_hash}

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(raw_entry) + "\n")

        return _entry_from_raw(raw_entry)

    def replay(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        entries: list[LedgerEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    raw = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"Invalid JSON at ledger line {line_number}") from exc
                entries.append(_entry_from_raw(raw))
        return entries

    def verify(self) -> bool:
        entries = self.replay()
        previous_hash: str | None = None
        for expected_sequence, entry in enumerate(entries, start=1):
            if entry.sequence != expected_sequence:
                raise LedgerError(f"Ledger sequence mismatch at entry {expected_sequence}")
            if entry.previous_entry_sha256 != previous_hash:
                raise LedgerError(f"Ledger chain mismatch at entry {entry.sequence}")
            expected_payload_hash = sha256_payload(entry.payload)
            if entry.payload_sha256 != expected_payload_hash:
                raise LedgerError(f"Payload hash mismatch at entry {entry.sequence}")
            entry_without_hash = {
                "sequence": entry.sequence,
                "event_type": entry.event_type,
                "task_id": entry.task_id,
                "occurred_at": entry.occurred_at,
                "payload": entry.payload,
                "payload_sha256": entry.payload_sha256,
                "previous_entry_sha256": entry.previous_entry_sha256,
            }
            expected_entry_hash = sha256_payload(entry_without_hash)
            if entry.entry_sha256 != expected_entry_hash:
                raise LedgerError(f"Entry hash mismatch at entry {entry.sequence}")
            previous_hash = entry.entry_sha256
        return True


def _entry_from_raw(raw: dict[str, Any]) -> LedgerEntry:
    required = [
        "sequence",
        "event_type",
        "task_id",
        "occurred_at",
        "payload",
        "payload_sha256",
        "previous_entry_sha256",
        "entry_sha256",
    ]
    missing = [key for key in required if key not in raw]
    if missing:
        raise LedgerError(f"Ledger entry missing required fields: {', '.join(missing)}")
    if not isinstance(raw["payload"], dict):
        raise LedgerError("Ledger entry payload must be an object")
    return LedgerEntry(
        sequence=int(raw["sequence"]),
        event_type=str(raw["event_type"]),
        task_id=str(raw["task_id"]),
        occurred_at=str(raw["occurred_at"]),
        payload=raw["payload"],
        payload_sha256=str(raw["payload_sha256"]),
        previous_entry_sha256=raw["previous_entry_sha256"],
        entry_sha256=str(raw["entry_sha256"]),
    )
