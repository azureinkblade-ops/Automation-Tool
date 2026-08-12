"""Local gate for deciding whether Hermes review may begin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .evidence import EvidencePackageBuilder
from .evidence_staleness import EvidenceStalenessChecker, EvidenceStalenessReport
from .schemas import SchemaCatalog
from .state_machine import ArtifactBundle, StateTransitionError, validate_transition


@dataclass(frozen=True)
class ReviewEligibilityDecision:
    eligible: bool
    from_state: str
    target_state: str
    task_id: str | None
    evidence_package_id: str | None
    reasons: list[str]
    staleness: EvidenceStalenessReport


class ReviewEligibilityGate:
    """Check freshness and state-machine rules before review starts."""

    target_state = "UNDER_REVIEW"

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.builder = EvidencePackageBuilder(catalog, base_dir=self.base_dir)
        self.staleness_checker = EvidenceStalenessChecker(catalog, base_dir=self.base_dir)

    def check(
        self,
        *,
        current_state: str,
        evidence_path: Path | str,
        parent_ref: str | None,
    ) -> ReviewEligibilityDecision:
        staleness = self.staleness_checker.check(evidence_path)
        reasons: list[str] = []

        if not staleness.review_eligible:
            reasons.extend(staleness.issues or ["Evidence is stale"])
            return self._decision(False, current_state, staleness, reasons)

        package = self.builder.load(evidence_path)
        try:
            validate_transition(
                current_state,
                self.target_state,
                ArtifactBundle(evidence=package.document, event_parent_ref=parent_ref),
                self.catalog,
            )
        except StateTransitionError as exc:
            reasons.append(str(exc))
            return self._decision(False, current_state, staleness, reasons)

        return self._decision(True, current_state, staleness, ["review eligible"])

    def _decision(
        self,
        eligible: bool,
        from_state: str,
        staleness: EvidenceStalenessReport,
        reasons: list[str],
    ) -> ReviewEligibilityDecision:
        return ReviewEligibilityDecision(
            eligible=eligible,
            from_state=from_state,
            target_state=self.target_state,
            task_id=staleness.task_id,
            evidence_package_id=staleness.evidence_package_id,
            reasons=reasons,
            staleness=staleness,
        )

