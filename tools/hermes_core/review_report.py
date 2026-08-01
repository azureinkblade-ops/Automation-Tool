"""Validate Hermes review reports against frozen evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .evidence import EvidencePackageBuilder, EvidencePackageError
from .schemas import SchemaCatalog, SchemaValidationError


class ReviewReportError(ValueError):
    """Raised when a Hermes review report is not acceptable."""


@dataclass(frozen=True)
class ReviewReportValidation:
    valid: bool
    review_id: str | None
    task_id: str | None
    evidence_package_id: str | None
    reviewer_agent_id: str | None
    recommendation: str | None
    finding_count: int
    issues: list[str]


class ReviewReportValidator:
    """Validate reviewer output without granting it authority."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.evidence_builder = EvidencePackageBuilder(catalog, base_dir=self.base_dir)

    def validate(
        self,
        review: dict[str, Any] | Path | str,
        *,
        evidence_path: Path | str,
    ) -> ReviewReportValidation:
        document = self._load_review(review)
        issues: list[str] = []

        try:
            self.catalog.validate("hermes.review", document)
        except SchemaValidationError as exc:
            issues.append(str(exc))

        evidence_document: dict[str, Any] | None = None
        try:
            package = self.evidence_builder.load(evidence_path)
            self.evidence_builder.verify(package)
            evidence_document = package.document
        except (EvidencePackageError, SchemaValidationError) as exc:
            issues.append(f"Evidence package invalid: {exc}")

        if "recommendation" not in document or document.get("recommendation") is None:
            issues.append("hermes.review.recommendation is required for review decisions")

        if evidence_document is not None:
            self._validate_evidence_binding(document, evidence_document, issues)
            self._validate_evidence_refs(document, evidence_document, issues)

        self._validate_timing(document, issues)
        self._validate_finding_ids(document, issues)
        self._validate_authority(document, issues)

        return ReviewReportValidation(
            valid=not issues,
            review_id=_string_or_none(document.get("review_id")),
            task_id=_string_or_none(document.get("task_id")),
            evidence_package_id=_string_or_none(document.get("evidence_package_id")),
            reviewer_agent_id=_string_or_none(
                (document.get("reviewer") or {}).get("agent_id")
                if isinstance(document.get("reviewer"), dict)
                else None
            ),
            recommendation=_string_or_none(document.get("recommendation")),
            finding_count=len(document.get("findings") or [])
            if isinstance(document.get("findings"), list)
            else 0,
            issues=issues,
        )

    def _load_review(self, review: dict[str, Any] | Path | str) -> dict[str, Any]:
        if isinstance(review, dict):
            return review

        path = Path(review)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReviewReportError(f"Review report is not valid JSON: {path}") from exc
        if not isinstance(document, dict):
            raise ReviewReportError("Review report must be a JSON object")
        return document

    def _validate_evidence_binding(
        self,
        review: dict[str, Any],
        evidence: dict[str, Any],
        issues: list[str],
    ) -> None:
        if review.get("task_id") != evidence.get("task_id"):
            issues.append("Review task_id does not match evidence package task_id")
        if review.get("evidence_package_id") != evidence.get("evidence_package_id"):
            issues.append("Review evidence_package_id does not match evidence package")

    def _validate_evidence_refs(
        self,
        review: dict[str, Any],
        evidence: dict[str, Any],
        issues: list[str],
    ) -> None:
        inventory = evidence.get("inventory") or []
        artifact_ids = {
            item.get("artifact_id")
            for item in inventory
            if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
        }
        for finding in review.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("finding_id", "<unknown>")
            for evidence_ref in finding.get("evidence_refs") or []:
                if evidence_ref not in artifact_ids:
                    issues.append(
                        f"Finding {finding_id} references unknown evidence artifact: {evidence_ref}"
                    )

    def _validate_timing(self, review: dict[str, Any], issues: list[str]) -> None:
        started_at = review.get("started_at")
        completed_at = review.get("completed_at")
        if not isinstance(started_at, str) or not isinstance(completed_at, str):
            return
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        except ValueError:
            return
        if completed < started:
            issues.append("Review completed_at must not be earlier than started_at")

    def _validate_finding_ids(self, review: dict[str, Any], issues: list[str]) -> None:
        seen: set[str] = set()
        for finding in review.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            finding_id = finding.get("finding_id")
            if not isinstance(finding_id, str):
                continue
            if finding_id in seen:
                issues.append(f"Duplicate finding_id: {finding_id}")
            seen.add(finding_id)

    def _validate_authority(self, review: dict[str, Any], issues: list[str]) -> None:
        authority = review.get("authority")
        if not isinstance(authority, dict):
            return
        prohibited = {
            "can_modify_state": authority.get("can_modify_state"),
            "can_authorize_execution": authority.get("can_authorize_execution"),
            "can_execute": authority.get("can_execute"),
        }
        for key, value in prohibited.items():
            if value is not False:
                issues.append(f"Review authority.{key} must be false")


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
