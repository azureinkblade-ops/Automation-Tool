"""Build and verify frozen Hermes evidence packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_file, sha256_payload
from .schemas import SchemaCatalog


class EvidencePackageError(ValueError):
    """Raised when evidence package creation or verification fails."""


@dataclass(frozen=True)
class EvidencePackage:
    document: dict[str, Any]
    path: Path | None = None

    @property
    def evidence_package_id(self) -> str:
        return str(self.document["evidence_package_id"])

    @property
    def package_sha256(self) -> str:
        return str(self.document["package_sha256"])


class EvidencePackageBuilder:
    """Create frozen evidence package documents from local files."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)

    def build(
        self,
        *,
        task_id: str,
        artifacts: list[Path | str],
        evidence_package_id: str | None = None,
        created_at: str | None = None,
        generated_by: str = "hermes",
        notes: str = "",
    ) -> EvidencePackage:
        if not artifacts:
            raise EvidencePackageError("Evidence package requires at least one artifact")

        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        inventory = [
            self._inventory_item(index + 1, artifact)
            for index, artifact in enumerate(artifacts)
        ]
        package_id = evidence_package_id or _default_package_id(task_id, inventory)
        without_hash = {
            "evidence_package_id": package_id,
            "task_id": task_id,
            "created_at": timestamp,
            "inventory": inventory,
            "frozen": True,
            "generated_by": generated_by,
            "notes": notes,
        }
        document = {
            **without_hash,
            "package_sha256": sha256_payload(without_hash),
        }
        self.catalog.validate("hermes.evidence", document)
        return EvidencePackage(document=document)

    def freeze_to_file(
        self,
        output_path: Path | str,
        *,
        task_id: str,
        artifacts: list[Path | str],
        evidence_package_id: str | None = None,
        created_at: str | None = None,
        generated_by: str = "hermes",
        notes: str = "",
    ) -> EvidencePackage:
        package = self.build(
            task_id=task_id,
            artifacts=artifacts,
            evidence_package_id=evidence_package_id,
            created_at=created_at,
            generated_by=generated_by,
            notes=notes,
        )
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(package.document) + "\n", encoding="utf-8")
        return EvidencePackage(document=package.document, path=target)

    def load(self, package_path: Path | str) -> EvidencePackage:
        path = Path(package_path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EvidencePackageError(f"Evidence package is not valid JSON: {path}") from exc
        if not isinstance(document, dict):
            raise EvidencePackageError("Evidence package must be a JSON object")
        return EvidencePackage(document=document, path=path)

    def verify(self, package: EvidencePackage | Path | str) -> bool:
        evidence_package = self.load(package) if not isinstance(package, EvidencePackage) else package
        document = evidence_package.document
        self.catalog.validate("hermes.evidence", document)

        expected_without_hash = {
            key: value
            for key, value in document.items()
            if key != "package_sha256"
        }
        if document["package_sha256"] != sha256_payload(expected_without_hash):
            raise EvidencePackageError("Evidence package hash mismatch")

        if document.get("frozen") is not True:
            raise EvidencePackageError("Evidence package is not frozen")

        inventory = document.get("inventory")
        if not isinstance(inventory, list):
            raise EvidencePackageError("Evidence package inventory must be a list")

        for item in inventory:
            self._verify_inventory_item(item)
        return True

    def _inventory_item(self, sequence: int, artifact: Path | str) -> dict[str, str]:
        artifact_path = Path(artifact)
        resolved = artifact_path if artifact_path.is_absolute() else self.base_dir / artifact_path
        if not resolved.exists() or not resolved.is_file():
            raise EvidencePackageError(f"Evidence artifact not found: {resolved}")

        path_or_uri = str(artifact_path)
        artifact_id = f"artifact-{sequence:04d}-{sha256_payload(path_or_uri)[:12]}"
        return {
            "artifact_id": artifact_id,
            "path_or_uri": path_or_uri,
            "sha256": sha256_file(resolved),
            "artifact_type": resolved.suffix.lstrip(".") or "file",
        }

    def _verify_inventory_item(self, item: Any) -> None:
        if not isinstance(item, dict):
            raise EvidencePackageError("Evidence inventory item must be an object")
        for key in ("artifact_id", "path_or_uri", "sha256"):
            if not isinstance(item.get(key), str) or not item.get(key):
                raise EvidencePackageError(f"Evidence inventory item missing {key}")

        artifact_path = Path(item["path_or_uri"])
        resolved = artifact_path if artifact_path.is_absolute() else self.base_dir / artifact_path
        if not resolved.exists() or not resolved.is_file():
            raise EvidencePackageError(f"Evidence artifact missing: {item['path_or_uri']}")
        if sha256_file(resolved) != item["sha256"]:
            raise EvidencePackageError(f"Evidence artifact hash mismatch: {item['artifact_id']}")


def _default_package_id(task_id: str, inventory: list[dict[str, str]]) -> str:
    seed = {
        "task_id": task_id,
        "inventory": inventory,
    }
    return f"evidence-{sha256_payload(seed)[:16]}"

