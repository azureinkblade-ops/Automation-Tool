"""Map the Phase 6B agreement classification to a terminal consensus disposition.

This is the third deterministic consensus primitive. It consumes the Phase 6B
``ConsensusEvaluation`` and the matching ``NormalizedFindingSet`` and maps them to a
terminal governance disposition under the frozen ADR-0003 policy.

It is deterministic, evidence-bound, auditable, read-only, and non-authoritative
with respect to execution. It must not generate acceptance artifacts (6D), mutate
Hermes state or append ledger events (6E), or authorize execution. An acceptance
disposition is explicitly not an execution authorization.

The repository already owns the terminal disposition vocabulary
(``consensus.schema.yaml`` enum ``[ACCEPTED, REJECTED, ESCALATED, BLOCKED,
INCONCLUSIVE]``); this module reuses it and does not invent parallel names.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .consensus_evaluator import (
    ConsensusEvaluation,
    ConsensusEvaluationError,
    MATERIAL_DISAGREEMENT,
    UNANIMOUS_CLEAN,
    UNANIMOUS_FINDING,
    DETERMINISTIC_FAILURE,
)
from .finding_normalizer import NormalizedFindingSet
from .hashing import sha256_payload
from .schemas import SchemaCatalog

# Canonical terminal dispositions (consensus.schema.yaml enum, UPPERCASE).
DISPOSITION_ACCEPTED = "ACCEPTED"
DISPOSITION_REJECTED = "REJECTED"
DISPOSITION_ESCALATED = "ESCALATED"
DISPOSITION_BLOCKED = "BLOCKED"
DISPOSITION_INCONCLUSIVE = "INCONCLUSIVE"

# Recommendation -> disposition. Unanimous reviewers share exactly one value here,
# because 6B freezes `recommendations` as a sorted tuple of distinct values and
# only reports the unanimous classes when that tuple has a single element.
_RECOMMENDATION_DISPOSITION = {
    "accept": DISPOSITION_ACCEPTED,
    "reject": DISPOSITION_REJECTED,
    "escalate": DISPOSITION_ESCALATED,
    "inconclusive": DISPOSITION_INCONCLUSIVE,
}

# Severities that block acceptance under ADR-0003 ("no unresolved critical
# findings; no unresolved high findings"). Medium/low/info are not enumerated as
# blocking, so by the non-invention rule they do not block.
BLOCKING_SEVERITIES = frozenset({"critical", "high"})

# Deterministic reason codes (disposition layer; distinct from the 6B codes).
REASON_DETERMINISTIC_FAILURE = "deterministic_failure"
REASON_MATERIAL_DISAGREEMENT = "material_disagreement"
REASON_UNANIMOUS_CLEAN = "unanimous_clean"
REASON_UNANIMOUS_FINDING = "unanimous_finding"
REASON_CRITICAL_FINDING_PRESENT = "critical_finding_present"
REASON_HIGH_FINDING_PRESENT = "high_finding_present"
REASON_LOWER_SEVERITY_POLICY_RESOLVED = "lower_severity_policy_resolved"
REASON_UNANIMOUS_RECOMMENDATION = "unanimous_recommendation"
REASON_CONFIDENCE_THRESHOLD_NOT_DEFINED = "confidence_threshold_not_defined"


class ConsensusDispositionError(ValueError):
    """Raised when a terminal disposition cannot be calculated deterministically."""


@dataclass(frozen=True)
class ConsensusDisposition:
    """Deterministic terminal disposition for one frozen evidence package."""

    task_id: str
    evidence_package_id: str
    finding_set_sha256: str
    evaluation_sha256: str
    agreement_class: str
    disposition: str
    reason_codes: tuple[str, ...]
    relevant_finding_keys: tuple[str, ...]
    blocking_finding_keys: tuple[str, ...]
    blocking_severities: tuple[str, ...]
    confidence_policy_marker: dict[str, Any]
    disposition_sha256: str

    @property
    def is_blocked(self) -> bool:
        return self.disposition == DISPOSITION_BLOCKED

    @property
    def is_escalated(self) -> bool:
        return self.disposition == DISPOSITION_ESCALATED

    @property
    def is_accepted(self) -> bool:
        return self.disposition == DISPOSITION_ACCEPTED

    @property
    def is_rejected(self) -> bool:
        return self.disposition == DISPOSITION_REJECTED

    @property
    def is_inconclusive(self) -> bool:
        return self.disposition == DISPOSITION_INCONCLUSIVE

    def as_document(self) -> dict[str, Any]:
        return {**_disposition_document(self), "disposition_sha256": self.disposition_sha256}


class ConsensusDispositionEngine:
    """Map a 6B evaluation to a terminal disposition under frozen policy."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Any = None) -> None:
        # `base_dir` is accepted for API symmetry with the other engines but is
        # unused: 6C performs no filesystem access of its own.
        self.catalog = catalog

    def dispose(
        self,
        evaluation: ConsensusEvaluation,
        finding_set: NormalizedFindingSet,
        *,
        expected_review_count: int | None = None,
    ) -> ConsensusDisposition:
        if not isinstance(evaluation, ConsensusEvaluation):
            raise ConsensusDispositionError(
                "Consensus disposition requires a ConsensusEvaluation"
            )
        if not isinstance(finding_set, NormalizedFindingSet):
            raise ConsensusDispositionError(
                "Consensus disposition requires a NormalizedFindingSet"
            )
        if expected_review_count is not None and expected_review_count < 1:
            raise ConsensusDispositionError("expected_review_count must be at least 1")

        # --- bindings: the evaluation and the finding set must refer to the same
        # frozen evidence package, and both hashes must re-derive. ---
        if (
            finding_set.task_id != evaluation.task_id
            or finding_set.evidence_package_id != evaluation.evidence_package_id
        ):
            raise ConsensusDispositionError(
                "Finding set and evaluation do not bind to the same task/evidence package"
            )
        if finding_set.finding_set_sha256 != evaluation.finding_set_sha256:
            raise ConsensusDispositionError(
                "Finding set hash does not match the evaluation's recorded hash"
            )
        if expected_review_count is not None and (
            evaluation.expected_review_count != expected_review_count
        ):
            raise ConsensusDispositionError(
                "expected_review_count does not match the evaluation record"
            )

        # Re-derive both hashes rather than trusting the caller.
        if evaluation.evaluation_sha256 != sha256_payload(_evaluation_document(evaluation)):
            raise ConsensusDispositionError("Consensus evaluation hash does not verify")
        if finding_set.finding_set_sha256 != sha256_payload(_finding_set_document(finding_set)):
            raise ConsensusDispositionError("Normalized finding set hash does not verify")

        reasons: set[str] = set()
        agreement_class = evaluation.agreement_class

        if agreement_class == DETERMINISTIC_FAILURE:
            reasons.add(REASON_DETERMINISTIC_FAILURE)
            reasons.update(evaluation.reason_codes)
            disposition = DISPOSITION_BLOCKED
        elif agreement_class == MATERIAL_DISAGREEMENT:
            reasons.add(REASON_MATERIAL_DISAGREEMENT)
            reasons.update(evaluation.reason_codes)
            disposition = DISPOSITION_ESCALATED
        elif agreement_class == UNANIMOUS_CLEAN:
            reasons.add(REASON_UNANIMOUS_CLEAN)
            disposition, rec_reasons = self._disposition_for_recommendation(
                evaluation.recommendations
            )
            reasons.update(rec_reasons)
        elif agreement_class == UNANIMOUS_FINDING:
            reasons.add(REASON_UNANIMOUS_FINDING)
            disposition, finding_reasons = self._classify_unanimous_finding(
                finding_set, evaluation
            )
            reasons.update(finding_reasons)
        else:
            raise ConsensusDispositionError(
                f"Unknown agreement class: {agreement_class!r}"
            )

        # Confidence gating is deferred: record the dependency, never apply it.
        reasons.add(REASON_CONFIDENCE_THRESHOLD_NOT_DEFINED)

        blocking_keys, blocking_severities = self._blocking_findings(finding_set)

        disposition_result = ConsensusDisposition(
            task_id=evaluation.task_id,
            evidence_package_id=evaluation.evidence_package_id,
            finding_set_sha256=evaluation.finding_set_sha256,
            evaluation_sha256=evaluation.evaluation_sha256,
            agreement_class=agreement_class,
            disposition=disposition,
            reason_codes=tuple(sorted(reasons)),
            relevant_finding_keys=tuple(sorted(f.finding_key for f in finding_set.findings)),
            blocking_finding_keys=tuple(sorted(blocking_keys)),
            blocking_severities=tuple(sorted(blocking_severities)),
            confidence_policy_marker={
                "enforced": False,
                "reason": "numeric_threshold_not_defined",
            },
            disposition_sha256="",
        )
        return replace(
            disposition_result,
            disposition_sha256=sha256_payload(_disposition_document(disposition_result)),
        )

    def _disposition_for_recommendation(
        self, recommendations: tuple[str, ...]
    ) -> tuple[str, set[str]]:
        """Map a unanimous recommendation tuple (exactly one value) to disposition."""
        if len(recommendations) != 1:
            # Defensive: 6B only reports unanimous classes when this tuple is a
            # single element. A conflicting set should have been material_disagreement.
            raise ConsensusDispositionError(
                "Recommendation mapping requires a single unanimous value"
            )
        recommendation = recommendations[0]
        if recommendation not in _RECOMMENDATION_DISPOSITION:
            raise ConsensusDispositionError(
                f"Unknown recommendation value: {recommendation!r}"
            )
        return (
            _RECOMMENDATION_DISPOSITION[recommendation],
            {REASON_UNANIMOUS_RECOMMENDATION},
        )

    def _classify_unanimous_finding(
        self,
        finding_set: NormalizedFindingSet,
        evaluation: ConsensusEvaluation,
    ) -> tuple[str, set[str]]:
        """Apply the critical/high blocking rule, then the recommendation mapping.

        ADR-0003 blocks on *any* unresolved critical OR high finding. When both
        severities are present, both reason codes are reported; the disposition is
        BLOCKED either way, so precedence only affects which reasons are listed.
        """
        severities = {finding.severity for finding in finding_set.findings}
        reasons: set[str] = set()
        blocked = False
        if "critical" in severities:
            reasons.add(REASON_CRITICAL_FINDING_PRESENT)
            blocked = True
        if "high" in severities:
            reasons.add(REASON_HIGH_FINDING_PRESENT)
            blocked = True
        if blocked:
            return DISPOSITION_BLOCKED, reasons
        # Only medium/low/info findings present. ADR-0003 does not enumerate these
        # as blocking, so by the non-invention rule they do not block; the
        # disposition follows the unanimous recommendation.
        disposition, rec_reasons = self._disposition_for_recommendation(
            evaluation.recommendations
        )
        rec_reasons.add(REASON_LOWER_SEVERITY_POLICY_RESOLVED)
        return disposition, rec_reasons

    def _blocking_findings(
        self, finding_set: NormalizedFindingSet
    ) -> tuple[set[str], set[str]]:
        keys: set[str] = set()
        severities: set[str] = set()
        for finding in finding_set.findings:
            if finding.severity in BLOCKING_SEVERITIES:
                keys.add(finding.finding_key)
                severities.add(finding.severity)
        return keys, severities


def _disposition_document(disposition: ConsensusDisposition) -> dict[str, Any]:
    """Canonical pre-hash shape. The sole source of the public document too."""
    return {
        "task_id": disposition.task_id,
        "evidence_package_id": disposition.evidence_package_id,
        "finding_set_sha256": disposition.finding_set_sha256,
        "evaluation_sha256": disposition.evaluation_sha256,
        "agreement_class": disposition.agreement_class,
        "disposition": disposition.disposition,
        "reason_codes": list(disposition.reason_codes),
        "relevant_finding_keys": list(disposition.relevant_finding_keys),
        "blocking_finding_keys": list(disposition.blocking_finding_keys),
        "blocking_severities": list(disposition.blocking_severities),
        "confidence_policy_marker": disposition.confidence_policy_marker,
    }


def _evaluation_document(evaluation: ConsensusEvaluation) -> dict[str, Any]:
    """Re-derive the 6B canonical document to verify its hash."""
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


def _finding_set_document(finding_set: NormalizedFindingSet) -> dict[str, Any]:
    """Re-derive the 6A canonical document to verify its hash."""
    document = dict(finding_set.as_document())
    document.pop("finding_set_sha256", None)
    return document
