"""Normalize validated Hermes review findings into a canonical finding set.

This is the first deterministic consensus primitive. It is read-only,
evidence-bound, and non-authoritative: it never writes the ledger, never
transitions task state, and never produces acceptance or execution authority.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import sha256_payload
from .review_report import ReviewReportValidator
from .schemas import SchemaCatalog

# Severity ordering is taken from the hermes.review schema enum.
SEVERITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "info")

_WHITESPACE = re.compile(r"\s+")


class FindingNormalizationError(ValueError):
    """Raised when review findings cannot be normalized deterministically."""


@dataclass(frozen=True)
class FindingSource:
    """One reviewer's contribution to a normalized finding."""

    review_id: str
    finding_id: str
    reviewer_agent_id: str
    reviewer_model_id: str
    reviewer_role: str
    recommendation: str | None
    confidence: float | None

    def as_document(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "finding_id": self.finding_id,
            "reviewer_agent_id": self.reviewer_agent_id,
            "reviewer_model_id": self.reviewer_model_id,
            "reviewer_role": self.reviewer_role,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class NormalizedFinding:
    """A canonical finding coalesced across every reviewer that reported it."""

    finding_key: str
    severity: str
    summary: str
    evidence_refs: tuple[str, ...]
    sources: tuple[FindingSource, ...]

    @property
    def review_ids(self) -> tuple[str, ...]:
        return tuple(sorted({source.review_id for source in self.sources}))

    @property
    def reviewer_agent_ids(self) -> tuple[str, ...]:
        return tuple(sorted({source.reviewer_agent_id for source in self.sources}))

    @property
    def recommendations(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    source.recommendation
                    for source in self.sources
                    if source.recommendation is not None
                }
            )
        )

    def as_document(self) -> dict[str, Any]:
        return {
            "finding_key": self.finding_key,
            "severity": self.severity,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "sources": [source.as_document() for source in self.sources],
        }


@dataclass(frozen=True)
class NormalizedFindingSet:
    """Deterministic normalized finding set for one frozen evidence package."""

    task_id: str
    evidence_package_id: str
    review_ids: tuple[str, ...]
    findings: tuple[NormalizedFinding, ...]
    finding_set_sha256: str

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def as_document(self) -> dict[str, Any]:
        return {
            **_set_document(
                self.task_id,
                self.evidence_package_id,
                self.review_ids,
                self.findings,
            ),
            "finding_set_sha256": self.finding_set_sha256,
        }


class FindingNormalizer:
    """Turn validated review reports into a canonical normalized finding set."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.report_validator = ReviewReportValidator(catalog, base_dir=self.base_dir)

    def normalize(
        self,
        reviews: list[dict[str, Any] | Path | str],
        *,
        evidence_path: Path | str,
    ) -> NormalizedFindingSet:
        if not reviews:
            raise FindingNormalizationError(
                "Finding normalization requires at least one review report"
            )

        documents = [self._load_review(review) for review in reviews]
        self._require_validated(documents, evidence_path=evidence_path)

        task_id = self._require_shared(documents, "task_id")
        evidence_package_id = self._require_shared(documents, "evidence_package_id")

        groups: dict[str, _FindingGroup] = {}
        for document in documents:
            self._collect_findings(document, groups)

        findings = tuple(
            group.freeze() for group in sorted(groups.values(), key=_FindingGroup.sort_key)
        )
        review_ids = tuple(sorted({str(document["review_id"]) for document in documents}))
        return NormalizedFindingSet(
            task_id=task_id,
            evidence_package_id=evidence_package_id,
            review_ids=review_ids,
            findings=findings,
            finding_set_sha256=sha256_payload(
                _set_document(task_id, evidence_package_id, review_ids, findings)
            ),
        )

    def _load_review(self, review: dict[str, Any] | Path | str) -> dict[str, Any]:
        if isinstance(review, dict):
            return review

        path = Path(review)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FindingNormalizationError(f"Review report is not valid JSON: {path}") from exc
        except OSError as exc:
            raise FindingNormalizationError(f"Review report cannot be read: {path}") from exc
        if not isinstance(document, dict):
            raise FindingNormalizationError("Review report must be a JSON object")
        return document

    def _require_validated(
        self,
        documents: list[dict[str, Any]],
        *,
        evidence_path: Path | str,
    ) -> None:
        issues: list[str] = []
        for document in documents:
            result = self.report_validator.validate(document, evidence_path=evidence_path)
            if not result.valid:
                label = result.review_id or "<unknown review>"
                issues.extend(f"{label}: {issue}" for issue in result.issues)
        if issues:
            raise FindingNormalizationError(
                "Finding normalization requires validated review reports: " + "; ".join(issues)
            )

    def _require_shared(self, documents: list[dict[str, Any]], key: str) -> str:
        values = {document.get(key) for document in documents}
        if len(values) != 1:
            raise FindingNormalizationError(
                f"All review reports must share the same {key} for normalization"
            )
        value = values.pop()
        if not isinstance(value, str) or not value:
            raise FindingNormalizationError(f"Review reports are missing {key}")
        return value

    def _collect_findings(
        self,
        document: dict[str, Any],
        groups: dict[str, _FindingGroup],
    ) -> None:
        review_id = str(document["review_id"])
        reviewer = document.get("reviewer") or {}
        recommendation = document.get("recommendation")
        for finding in document.get("findings") or []:
            severity = str(finding["severity"])
            summary = _canonical_summary(finding["summary"])
            evidence_refs = tuple(sorted({str(ref) for ref in finding.get("evidence_refs") or []}))
            finding_key = _finding_key(severity, summary, evidence_refs)
            source = FindingSource(
                review_id=review_id,
                finding_id=str(finding["finding_id"]),
                reviewer_agent_id=str(reviewer.get("agent_id", "")),
                reviewer_model_id=str(reviewer.get("model_id", "")),
                reviewer_role=str(reviewer.get("role", "")),
                recommendation=_string_or_none(recommendation),
                confidence=_number_or_none(finding.get("confidence")),
            )

            group = groups.get(finding_key)
            if group is None:
                groups[finding_key] = _FindingGroup(
                    finding_key=finding_key,
                    severity=severity,
                    evidence_refs=evidence_refs,
                    summaries={summary},
                    sources=[source],
                )
            else:
                # Reviewers may word the same finding with different casing or spacing.
                # Every variant is kept so the representative summary can be chosen
                # deterministically, independent of the order reports arrived in.
                group.summaries.add(summary)
                group.sources.append(source)


@dataclass
class _FindingGroup:
    """Mutable accumulator for one coalescing finding. Frozen via freeze()."""

    finding_key: str
    severity: str
    evidence_refs: tuple[str, ...]
    summaries: set[str]
    sources: list[FindingSource]

    def freeze(self) -> NormalizedFinding:
        return NormalizedFinding(
            finding_key=self.finding_key,
            severity=self.severity,
            summary=min(self.summaries),
            evidence_refs=self.evidence_refs,
            sources=tuple(sorted(self.sources, key=lambda s: (s.review_id, s.finding_id))),
        )

    def sort_key(self) -> tuple[int, str]:
        rank = (
            SEVERITY_ORDER.index(self.severity)
            if self.severity in SEVERITY_ORDER
            else len(SEVERITY_ORDER)
        )
        return (rank, self.finding_key)


def _set_document(
    task_id: str,
    evidence_package_id: str,
    review_ids: tuple[str, ...],
    findings: tuple[NormalizedFinding, ...],
) -> dict[str, Any]:
    """Canonical pre-hash shape, shared by the hash and the public document."""
    return {
        "task_id": task_id,
        "evidence_package_id": evidence_package_id,
        "review_ids": list(review_ids),
        "findings": [finding.as_document() for finding in findings],
    }


def _canonical_summary(value: Any) -> str:
    return _WHITESPACE.sub(" ", str(value).strip())


def _finding_key(severity: str, summary: str, evidence_refs: tuple[str, ...]) -> str:
    identity = {
        "severity": severity,
        "summary": summary.casefold(),
        "evidence_refs": list(evidence_refs),
    }
    return f"finding-{sha256_payload(identity)[:16]}"


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
