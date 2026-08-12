"""Evaluate deterministic agreement/disagreement over normalized review findings.

This is the second deterministic consensus primitive. It consumes the normalized
finding set produced by the finding normalizer and classifies what the validated
reviewer inputs represent.

It is read-only, evidence-bound, and non-authoritative: it never writes the
ledger, never transitions task state, never produces an acceptance artifact or
terminal disposition, and never decides which reviewer is correct. Terminal
disposition is milestone 6C.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .finding_normalizer import NormalizedFindingSet
from .hashing import sha256_payload
from .review_report import ReviewReportValidator
from .schemas import SchemaCatalog

# Agreement classes. These describe the shape of the reviewer inputs and are
# deliberately distinct from the terminal disposition vocabulary
# (ACCEPTED/ESCALATED/BLOCKED/INCONCLUSIVE) owned by ADR-0003 and mapped by 6C.
UNANIMOUS_CLEAN = "unanimous_clean"
UNANIMOUS_FINDING = "unanimous_finding"
MATERIAL_DISAGREEMENT = "material_disagreement"
DETERMINISTIC_FAILURE = "deterministic_failure"

# Deterministic reason codes.
REASON_FINDING_COVERAGE_CONFLICT = "finding_coverage_conflict"
REASON_RECOMMENDATION_CONFLICT = "recommendation_conflict"
REASON_MISSING_REQUIRED_REVIEW = "missing_required_review"
REASON_DUPLICATE_REVIEW_ID = "duplicate_review_id"
REASON_DUPLICATE_REVIEWER_IDENTITY = "duplicate_reviewer_identity"
REASON_TASK_ID_MISMATCH = "task_id_mismatch"
REASON_EVIDENCE_PACKAGE_MISMATCH = "evidence_package_mismatch"
REASON_REVIEW_ID_MISMATCH = "review_id_mismatch"
REASON_FINDING_SET_HASH_MISMATCH = "finding_set_hash_mismatch"
REASON_INVALID_REVIEW_REPORT = "invalid_review_report"


class ConsensusEvaluationError(ValueError):
    """Raised when consensus agreement cannot be evaluated deterministically."""


@dataclass(frozen=True)
class FindingAgreement:
    """Reviewer coverage for one normalized finding."""

    finding_key: str
    severity: str
    reporting_review_ids: tuple[str, ...]
    silent_review_ids: tuple[str, ...]
    unanimous: bool

    def as_document(self) -> dict[str, Any]:
        return {
            "finding_key": self.finding_key,
            "severity": self.severity,
            "reporting_review_ids": list(self.reporting_review_ids),
            "silent_review_ids": list(self.silent_review_ids),
            "unanimous": self.unanimous,
        }


@dataclass(frozen=True)
class ConsensusEvaluation:
    """Deterministic agreement classification for one frozen evidence package."""

    task_id: str
    evidence_package_id: str
    finding_set_sha256: str
    agreement_class: str
    review_ids: tuple[str, ...]
    reviewer_agent_ids: tuple[str, ...]
    expected_review_count: int | None
    finding_agreements: tuple[FindingAgreement, ...]
    recommendations: tuple[str, ...]
    recommendation_conflict: bool
    reason_codes: tuple[str, ...]
    evaluation_sha256: str

    @property
    def agreed(self) -> bool:
        """True only for the two unanimous classes. Not an acceptance decision."""
        return self.agreement_class in (UNANIMOUS_CLEAN, UNANIMOUS_FINDING)

    def as_document(self) -> dict[str, Any]:
        return {**_evaluation_document(self), "evaluation_sha256": self.evaluation_sha256}


class ConsensusEvaluator:
    """Classify agreement over a normalized finding set and validated reviews."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.report_validator = ReviewReportValidator(catalog, base_dir=self.base_dir)

    def evaluate(
        self,
        finding_set: NormalizedFindingSet,
        reviews: list[dict[str, Any] | Path | str],
        *,
        evidence_path: Path | str,
        expected_review_count: int | None = None,
    ) -> ConsensusEvaluation:
        if not isinstance(finding_set, NormalizedFindingSet):
            raise ConsensusEvaluationError(
                "Consensus evaluation requires a NormalizedFindingSet"
            )
        if not reviews:
            raise ConsensusEvaluationError(
                "Consensus evaluation requires at least one review report"
            )
        if expected_review_count is not None and expected_review_count < 1:
            raise ConsensusEvaluationError("expected_review_count must be at least 1")

        documents = [self._load_review(review) for review in reviews]
        reasons: set[str] = set()

        # Structural checks first: a broken input set cannot meaningfully agree.
        reasons.update(self._check_reports_valid(documents, evidence_path=evidence_path))
        reasons.update(self._check_identity(documents, finding_set))
        reasons.update(self._check_finding_set_integrity(finding_set))
        reasons.update(self._check_population(documents, expected_review_count))

        review_ids = tuple(sorted({str(document.get("review_id", "")) for document in documents}))
        reviewer_agent_ids = tuple(
            sorted(
                {
                    str((document.get("reviewer") or {}).get("agent_id", ""))
                    for document in documents
                }
            )
        )
        recommendations = tuple(
            sorted(
                {
                    str(document["recommendation"])
                    for document in documents
                    if isinstance(document.get("recommendation"), str)
                }
            )
        )
        recommendation_conflict = len(recommendations) > 1
        if recommendation_conflict:
            reasons.add(REASON_RECOMMENDATION_CONFLICT)

        finding_agreements = self._finding_agreements(finding_set, review_ids)
        if any(not agreement.unanimous for agreement in finding_agreements):
            reasons.add(REASON_FINDING_COVERAGE_CONFLICT)

        # Build once with a placeholder hash, then seal it from its own document,
        # so the hashed shape and the public shape can never drift apart.
        evaluation = ConsensusEvaluation(
            task_id=finding_set.task_id,
            evidence_package_id=finding_set.evidence_package_id,
            finding_set_sha256=finding_set.finding_set_sha256,
            agreement_class=_classify(reasons, finding_agreements),
            review_ids=review_ids,
            reviewer_agent_ids=reviewer_agent_ids,
            expected_review_count=expected_review_count,
            finding_agreements=finding_agreements,
            recommendations=recommendations,
            recommendation_conflict=recommendation_conflict,
            reason_codes=tuple(sorted(reasons)),
            evaluation_sha256="",
        )
        return replace(
            evaluation,
            evaluation_sha256=sha256_payload(_evaluation_document(evaluation)),
        )

    def _load_review(self, review: dict[str, Any] | Path | str) -> dict[str, Any]:
        if isinstance(review, dict):
            return review

        path = Path(review)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConsensusEvaluationError(f"Review report is not valid JSON: {path}") from exc
        except OSError as exc:
            raise ConsensusEvaluationError(f"Review report cannot be read: {path}") from exc
        if not isinstance(document, dict):
            raise ConsensusEvaluationError("Review report must be a JSON object")
        return document

    def _check_reports_valid(
        self,
        documents: list[dict[str, Any]],
        *,
        evidence_path: Path | str,
    ) -> set[str]:
        for document in documents:
            result = self.report_validator.validate(document, evidence_path=evidence_path)
            if not result.valid:
                return {REASON_INVALID_REVIEW_REPORT}
        return set()

    def _check_identity(
        self,
        documents: list[dict[str, Any]],
        finding_set: NormalizedFindingSet,
    ) -> set[str]:
        reasons: set[str] = set()

        task_ids = {str(document.get("task_id", "")) for document in documents}
        if task_ids != {finding_set.task_id}:
            reasons.add(REASON_TASK_ID_MISMATCH)

        package_ids = {str(document.get("evidence_package_id", "")) for document in documents}
        if package_ids != {finding_set.evidence_package_id}:
            reasons.add(REASON_EVIDENCE_PACKAGE_MISMATCH)

        review_ids = [str(document.get("review_id", "")) for document in documents]
        if len(set(review_ids)) != len(review_ids):
            reasons.add(REASON_DUPLICATE_REVIEW_ID)
        if set(review_ids) != set(finding_set.review_ids):
            reasons.add(REASON_REVIEW_ID_MISMATCH)

        agent_ids = [
            str((document.get("reviewer") or {}).get("agent_id", "")) for document in documents
        ]
        if len(set(agent_ids)) != len(agent_ids):
            reasons.add(REASON_DUPLICATE_REVIEWER_IDENTITY)

        return reasons

    def _check_finding_set_integrity(self, finding_set: NormalizedFindingSet) -> set[str]:
        # Re-derive the 6A set hash from the set's own contents. The pre-hash
        # document is the public document minus the hash field itself, matching
        # how the normalizer computes it.
        document = dict(finding_set.as_document())
        recorded = document.pop("finding_set_sha256", None)
        if recorded != sha256_payload(document):
            return {REASON_FINDING_SET_HASH_MISMATCH}
        return set()

    def _check_population(
        self,
        documents: list[dict[str, Any]],
        expected_review_count: int | None,
    ) -> set[str]:
        if expected_review_count is None:
            return set()
        distinct = {str(document.get("review_id", "")) for document in documents}
        if len(distinct) < expected_review_count:
            return {REASON_MISSING_REQUIRED_REVIEW}
        return set()

    def _finding_agreements(
        self,
        finding_set: NormalizedFindingSet,
        review_ids: tuple[str, ...],
    ) -> tuple[FindingAgreement, ...]:
        population = set(review_ids)
        agreements = []
        for finding in finding_set.findings:
            reporting = {source.review_id for source in finding.sources}
            silent = population - reporting
            agreements.append(
                FindingAgreement(
                    finding_key=finding.finding_key,
                    severity=finding.severity,
                    reporting_review_ids=tuple(sorted(reporting)),
                    silent_review_ids=tuple(sorted(silent)),
                    unanimous=not silent,
                )
            )
        # Findings arrive already deterministically ordered from 6A; sorting by
        # finding_key keeps this layer independent of that guarantee.
        return tuple(sorted(agreements, key=lambda item: item.finding_key))


def _classify(
    reasons: set[str],
    finding_agreements: tuple[FindingAgreement, ...],
) -> str:
    """Fixed precedence: structural failure, then disagreement, then agreement."""
    structural = {
        REASON_MISSING_REQUIRED_REVIEW,
        REASON_DUPLICATE_REVIEW_ID,
        REASON_DUPLICATE_REVIEWER_IDENTITY,
        REASON_TASK_ID_MISMATCH,
        REASON_EVIDENCE_PACKAGE_MISMATCH,
        REASON_REVIEW_ID_MISMATCH,
        REASON_FINDING_SET_HASH_MISMATCH,
        REASON_INVALID_REVIEW_REPORT,
    }
    if reasons & structural:
        return DETERMINISTIC_FAILURE
    if REASON_FINDING_COVERAGE_CONFLICT in reasons or REASON_RECOMMENDATION_CONFLICT in reasons:
        return MATERIAL_DISAGREEMENT
    if finding_agreements:
        return UNANIMOUS_FINDING
    return UNANIMOUS_CLEAN


def _evaluation_document(evaluation: ConsensusEvaluation) -> dict[str, Any]:
    """Canonical pre-hash shape. The sole source of the public document too."""
    return {
        "task_id": evaluation.task_id,
        "evidence_package_id": evaluation.evidence_package_id,
        "finding_set_sha256": evaluation.finding_set_sha256,
        "agreement_class": evaluation.agreement_class,
        "review_ids": list(evaluation.review_ids),
        "reviewer_agent_ids": list(evaluation.reviewer_agent_ids),
        "expected_review_count": evaluation.expected_review_count,
        "finding_agreements": [item.as_document() for item in evaluation.finding_agreements],
        "recommendations": list(evaluation.recommendations),
        "recommendation_conflict": evaluation.recommendation_conflict,
        "reason_codes": list(evaluation.reason_codes),
    }
