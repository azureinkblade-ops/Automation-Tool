"""Report whether frozen Hermes evidence is stale."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import sha256_file, sha256_payload
from .schemas import SchemaCatalog, SchemaValidationError


@dataclass(frozen=True)
class ArtifactStaleness:
    artifact_id: str
    path_or_uri: str
    expected_sha256: str
    actual_sha256: str | None
    status: str


@dataclass(frozen=True)
class EvidenceStalenessReport:
    evidence_package_id: str | None
    task_id: str | None
    stale: bool
    review_eligible: bool
    package_hash_matches: bool
    schema_valid: bool
    artifacts: list[ArtifactStaleness]
    issues: list[str]


class EvidenceStalenessChecker:
    """Inspect a frozen evidence package without mutating it."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)

    def check(self, package_path: Path | str) -> EvidenceStalenessReport:
        path = Path(package_path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _failed_report(f"Evidence package cannot be read: {exc}")
        if not isinstance(document, dict):
            return _failed_report("Evidence package must be a JSON object")

        issues: list[str] = []
        schema_valid = True
        try:
            self.catalog.validate("hermes.evidence", document)
        except SchemaValidationError as exc:
            schema_valid = False
            issues.append(str(exc))

        package_hash_matches = _package_hash_matches(document)
        if not package_hash_matches:
            issues.append("Evidence package hash mismatch")

        artifacts: list[ArtifactStaleness] = []
        inventory = document.get("inventory")
        if isinstance(inventory, list):
            artifacts = [self._artifact_status(item, issues) for item in inventory]
        else:
            issues.append("Evidence package inventory must be a list")

        stale = bool(issues) or any(item.status != "ok" for item in artifacts)
        return EvidenceStalenessReport(
            evidence_package_id=_optional_str(document.get("evidence_package_id")),
            task_id=_optional_str(document.get("task_id")),
            stale=stale,
            review_eligible=not stale,
            package_hash_matches=package_hash_matches,
            schema_valid=schema_valid,
            artifacts=artifacts,
            issues=issues,
        )

    def _artifact_status(self, item: Any, issues: list[str]) -> ArtifactStaleness:
        if not isinstance(item, dict):
            issues.append("Evidence inventory item must be an object")
            return ArtifactStaleness("", "", "", None, "changed")

        artifact_id = str(item.get("artifact_id") or "")
        path_or_uri = str(item.get("path_or_uri") or "")
        expected_sha256 = str(item.get("sha256") or "")
        artifact_path = Path(path_or_uri)
        resolved = artifact_path if artifact_path.is_absolute() else self.base_dir / artifact_path

        if not resolved.exists() or not resolved.is_file():
            issues.append(f"Evidence artifact missing: {path_or_uri}")
            return ArtifactStaleness(artifact_id, path_or_uri, expected_sha256, None, "missing")

        actual_sha256 = sha256_file(resolved)
        if actual_sha256 != expected_sha256:
            issues.append(f"Evidence artifact hash mismatch: {artifact_id}")
            return ArtifactStaleness(artifact_id, path_or_uri, expected_sha256, actual_sha256, "changed")

        return ArtifactStaleness(artifact_id, path_or_uri, expected_sha256, actual_sha256, "ok")


def _package_hash_matches(document: dict[str, Any]) -> bool:
    if not isinstance(document.get("package_sha256"), str):
        return False
    without_hash = {
        key: value
        for key, value in document.items()
        if key != "package_sha256"
    }
    return document["package_sha256"] == sha256_payload(without_hash)


def _failed_report(issue: str) -> EvidenceStalenessReport:
    return EvidenceStalenessReport(
        evidence_package_id=None,
        task_id=None,
        stale=True,
        review_eligible=False,
        package_hash_matches=False,
        schema_valid=False,
        artifacts=[],
        issues=[issue],
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

