"""Local artifact registry for Hermes evidence and governance files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_file, sha256_payload


class ArtifactRegistryError(ValueError):
    """Raised when artifact registration or verification fails."""


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    path: str
    schema_name: str
    sha256: str
    registered_at: str
    metadata: dict[str, Any]
    record_sha256: str


class ArtifactRegistry:
    """JSON-backed artifact registry with deterministic record hashes."""

    def __init__(self, path: Path | str, *, base_dir: Path | str | None = None) -> None:
        self.path = Path(path)
        self.base_dir = Path(base_dir) if base_dir is not None else self.path.parent

    def register(
        self,
        artifact_path: Path | str,
        *,
        artifact_id: str,
        schema_name: str,
        metadata: dict[str, Any] | None = None,
        registered_at: str | None = None,
    ) -> ArtifactRecord:
        target = Path(artifact_path)
        resolved = target if target.is_absolute() else self.base_dir / target
        if not resolved.exists():
            raise ArtifactRegistryError(f"Artifact not found: {resolved}")

        relative_path = str(target)
        timestamp = registered_at or datetime.now(timezone.utc).isoformat()
        digest = sha256_file(resolved)
        record_without_hash = {
            "artifact_id": artifact_id,
            "path": relative_path,
            "schema_name": schema_name,
            "sha256": digest,
            "registered_at": timestamp,
            "metadata": metadata or {},
        }
        record_hash = sha256_payload(record_without_hash)
        raw_record = {**record_without_hash, "record_sha256": record_hash}

        records = {record.artifact_id: record for record in self.list_records()}
        records[artifact_id] = _record_from_raw(raw_record)
        self._write_records(list(records.values()))
        return records[artifact_id]

    def list_records(self) -> list[ArtifactRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ArtifactRegistryError("Artifact registry is not valid JSON") from exc
        if not isinstance(raw, list):
            raise ArtifactRegistryError("Artifact registry must be a list")
        return [_record_from_raw(item) for item in raw]

    def get(self, artifact_id: str) -> ArtifactRecord:
        for record in self.list_records():
            if record.artifact_id == artifact_id:
                return record
        raise ArtifactRegistryError(f"Artifact is not registered: {artifact_id}")

    def verify(self, artifact_id: str | None = None) -> bool:
        records = [self.get(artifact_id)] if artifact_id else self.list_records()
        for record in records:
            self._verify_record(record)
        return True

    def _verify_record(self, record: ArtifactRecord) -> None:
        expected_without_hash = {
            "artifact_id": record.artifact_id,
            "path": record.path,
            "schema_name": record.schema_name,
            "sha256": record.sha256,
            "registered_at": record.registered_at,
            "metadata": record.metadata,
        }
        expected_record_hash = sha256_payload(expected_without_hash)
        if record.record_sha256 != expected_record_hash:
            raise ArtifactRegistryError(f"Record hash mismatch: {record.artifact_id}")

        artifact_path = Path(record.path)
        resolved = artifact_path if artifact_path.is_absolute() else self.base_dir / artifact_path
        if not resolved.exists():
            raise ArtifactRegistryError(f"Artifact file missing: {record.path}")
        current_hash = sha256_file(resolved)
        if current_hash != record.sha256:
            raise ArtifactRegistryError(f"Artifact hash mismatch: {record.artifact_id}")

    def _write_records(self, records: list[ArtifactRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = [_record_to_raw(record) for record in sorted(records, key=lambda item: item.artifact_id)]
        self.path.write_text(canonical_json(raw) + "\n", encoding="utf-8")


def _record_from_raw(raw: dict[str, Any]) -> ArtifactRecord:
    required = [
        "artifact_id",
        "path",
        "schema_name",
        "sha256",
        "registered_at",
        "metadata",
        "record_sha256",
    ]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ArtifactRegistryError(f"Artifact record missing required fields: {', '.join(missing)}")
    if not isinstance(raw["metadata"], dict):
        raise ArtifactRegistryError("Artifact metadata must be an object")
    return ArtifactRecord(
        artifact_id=str(raw["artifact_id"]),
        path=str(raw["path"]),
        schema_name=str(raw["schema_name"]),
        sha256=str(raw["sha256"]),
        registered_at=str(raw["registered_at"]),
        metadata=raw["metadata"],
        record_sha256=str(raw["record_sha256"]),
    )


def _record_to_raw(record: ArtifactRecord) -> dict[str, Any]:
    return {
        "artifact_id": record.artifact_id,
        "path": record.path,
        "schema_name": record.schema_name,
        "sha256": record.sha256,
        "registered_at": record.registered_at,
        "metadata": record.metadata,
        "record_sha256": record.record_sha256,
    }
