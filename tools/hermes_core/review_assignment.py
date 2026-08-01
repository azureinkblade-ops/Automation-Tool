"""Build local Hermes review assignment plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .review_gate import ReviewEligibilityDecision, ReviewEligibilityGate
from .reviewer_registry import ReviewerAgent, ReviewerRegistry, ReviewerRegistryError
from .schemas import SchemaCatalog


class ReviewAssignmentError(ValueError):
    """Raised when a review assignment plan cannot be built."""


REVIEW_ROLES = {
    "reviewer",
    "architect_reviewer",
    "security_reviewer",
    "implementation_reviewer",
}

DEFAULT_REVIEW_ROLES = (
    "architect_reviewer",
    "security_reviewer",
    "implementation_reviewer",
)


@dataclass(frozen=True)
class ReviewerAssignment:
    agent_id: str
    model_id: str
    review_role: str
    evidence_package_id: str


@dataclass(frozen=True)
class ReviewAssignmentPlan:
    ready: bool
    task_id: str | None
    evidence_package_id: str | None
    reasons: list[str]
    gate: ReviewEligibilityDecision
    assignments: list[ReviewerAssignment]


class ReviewAssignmentBuilder:
    """Pair eligible evidence with active reviewers without running models."""

    def __init__(self, catalog: SchemaCatalog, *, base_dir: Path | str) -> None:
        self.catalog = catalog
        self.base_dir = Path(base_dir)
        self.gate = ReviewEligibilityGate(catalog, base_dir=self.base_dir)

    def build(
        self,
        *,
        current_state: str,
        evidence_path: Path | str,
        parent_ref: str | None,
        registry: ReviewerRegistry,
        minimum_reviewers: int = 3,
        review_roles: tuple[str, ...] = DEFAULT_REVIEW_ROLES,
    ) -> ReviewAssignmentPlan:
        if minimum_reviewers < 1:
            raise ReviewAssignmentError("minimum_reviewers must be at least 1")
        self._validate_review_roles(review_roles)

        gate = self.gate.check(
            current_state=current_state,
            evidence_path=evidence_path,
            parent_ref=parent_ref,
        )
        if not gate.eligible:
            return self._plan(False, gate, gate.reasons, [])

        try:
            reviewers = registry.require_active_count(minimum_reviewers)
        except ReviewerRegistryError as exc:
            return self._plan(False, gate, [str(exc)], [])

        selected = reviewers[:minimum_reviewers]
        assignments = [
            self._assignment(index, reviewer, gate.evidence_package_id, review_roles)
            for index, reviewer in enumerate(selected)
        ]
        return self._plan(True, gate, ["review assignments ready"], assignments)

    def _assignment(
        self,
        index: int,
        reviewer: ReviewerAgent,
        evidence_package_id: str | None,
        review_roles: tuple[str, ...],
    ) -> ReviewerAssignment:
        return ReviewerAssignment(
            agent_id=reviewer.agent_id,
            model_id=reviewer.model_id,
            review_role=review_roles[index] if index < len(review_roles) else "reviewer",
            evidence_package_id=evidence_package_id or "",
        )

    def _plan(
        self,
        ready: bool,
        gate: ReviewEligibilityDecision,
        reasons: list[str],
        assignments: list[ReviewerAssignment],
    ) -> ReviewAssignmentPlan:
        return ReviewAssignmentPlan(
            ready=ready,
            task_id=gate.task_id,
            evidence_package_id=gate.evidence_package_id,
            reasons=reasons,
            gate=gate,
            assignments=assignments,
        )

    def _validate_review_roles(self, review_roles: tuple[str, ...]) -> None:
        if not review_roles:
            raise ReviewAssignmentError("review_roles must not be empty")
        invalid = [role for role in review_roles if role not in REVIEW_ROLES]
        if invalid:
            raise ReviewAssignmentError(f"Unknown review role: {invalid[0]}")
