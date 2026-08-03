"""Validate Hermes review outcome records against frozen evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidencePackageBuilder, EvidencePackageError
from .review_report import ReviewReportValidator
from .schemas import SchemaCatalog, SchemaValidationError


class ReviewOutcomeError(ValueError):
    """Raised when a Hermes review outcome record is not acceptable."""


@dataclass(frozen=True)
class ReviewOutcomeValidation:
    valid: bool
    review_outcome_id: str | None
    task_id: str | None
    evidence_package_id: str | None
    status: str | None
    review_ids: list[str]
    issues: list[str]


class ReviewOutcomeValidator:
    """Validate a review outcome record without granting it authority."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.evidence_builder = EvidencePackageBuilder(catalog, base_dir=self.base_dir)
        self.report_validator = ReviewReportValidator(catalog, base_dir=self.base_dir)

    def validate(
        self,
        outcome: dict[str, Any] | Path | str,
        *,
        evidence_path: Path | str,
        reviews: list[dict[str, Any] | Path | str] | None = None,
    ) -> ReviewOutcomeValidation:
        document = self._load_outcome(outcome)
        issues: list[str] = []

        try:
            self.catalog.validate("hermes.review_outcome", document)
        except SchemaValidationError as exc:
            issues.append(str(exc))

        evidence_document: dict[str, Any] | None = None
        try:
            package = self.evidence_builder.load(evidence_path)
            self.evidence_builder.verify(package)
            evidence_document = package.document
        except (EvidencePackageError, SchemaValidationError) as exc:
            issues.append(f"Evidence package invalid: {exc}")

        review_ids = self._review_ids(document)
        if not review_ids:
            issues.append("Review outcome requires at least one review_id")

        if evidence_document is not None:
            self._validate_evidence_binding(document, evidence_document, issues)

        if reviews is None:
            reviews = []
        if not reviews:
            issues.append("Review outcome requires at least one validated review document")

        validated_reviews = []
        for review in reviews:
            result = self.report_validator.validate(review, evidence_path=evidence_path)
            if not result.valid:
                issues.extend(result.issues)
                continue
            validated_reviews.append(result)

        valid_review_ids = {
            result.review_id
            for result in validated_reviews
            if result.review_id is not None
        }
        for result in validated_reviews:
            if result.review_id is not None and result.review_id not in review_ids:
                issues.append(f"Review {result.review_id} is not referenced by the outcome")

        for review_id in review_ids:
            if review_id not in valid_review_ids:
                issues.append(f"Outcome references unknown review_id: {review_id}")

        self._validate_authority(document, issues)

        return ReviewOutcomeValidation(
            valid=not issues,
            review_outcome_id=_string_or_none(document.get("review_outcome_id")),
            task_id=_string_or_none(document.get("task_id")),
            evidence_package_id=_string_or_none(document.get("evidence_package_id")),
            status=_string_or_none(document.get("status")),
            review_ids=review_ids,
            issues=issues,
        )

    def _load_outcome(self, outcome: dict[str, Any] | Path | str) -> dict[str, Any]:
        if isinstance(outcome, dict):
            return outcome

        path = Path(outcome)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReviewOutcomeError(f"Review outcome is not valid JSON: {path}") from exc
        if not isinstance(document, dict):
            raise ReviewOutcomeError("Review outcome must be a JSON object")
        return document

    def _review_ids(self, document: dict[str, Any]) -> list[str]:
        review_ids = document.get("review_ids")
        if not isinstance(review_ids, list):
            return []
        normalized: list[str] = []
        for review_id in review_ids:
            if isinstance(review_id, str) and review_id:
                normalized.append(review_id)
        return normalized

    def _validate_evidence_binding(
        self,
        outcome: dict[str, Any],
        evidence: dict[str, Any],
        issues: list[str],
    ) -> None:
        if outcome.get("task_id") != evidence.get("task_id"):
            issues.append("Review outcome task_id does not match evidence package task_id")
        if outcome.get("evidence_package_id") != evidence.get("evidence_package_id"):
            issues.append("Review outcome evidence_package_id does not match evidence package")

    def _validate_authority(self, outcome: dict[str, Any], issues: list[str]) -> None:
        authority = outcome.get("authority")
        if not isinstance(authority, dict):
            return
        prohibited = {
            "can_modify_state": authority.get("can_modify_state"),
            "can_authorize_execution": authority.get("can_authorize_execution"),
            "can_execute": authority.get("can_execute"),
        }
        for key, value in prohibited.items():
            if value is not False:
                issues.append(f"Review outcome authority.{key} must be false")


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
