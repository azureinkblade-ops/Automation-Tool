"""Non-executing reviewer runner interface for Hermes.

This is a real orchestration path: it accepts a verified review-session envelope
and returns a status result for the task. It is explicitly NON-executing — its
own reason string declares "Model execution is not authorized in this phase".

As part of the Governance Consumer Integration Proof, the result is enriched
with authoritative Hermes governance status via the existing read-only consumer
``get_task_governance_status(task_id)``. This is observation only: the governance
status is surfaced for informational/orchestration visibility and is never read
to authorize or initiate execution. The architectural invariant
``ACCEPTED != EXECUTION AUTHORIZATION`` is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .governance_consumer import TaskGovernanceStatus, get_task_governance_status
from .review_session import ReviewSessionBuilder, ReviewSessionEnvelope


class ReviewRunnerError(ValueError):
    """Raised when a review runner cannot accept a session envelope."""


@dataclass(frozen=True)
class ReviewRunnerResult:
    status: str
    review_session_id: str
    task_id: str
    evidence_package_id: str
    assignment_count: int
    reason: str
    # Observational governance truth, attached by prepare(). Read-only; never
    # used to authorize execution. ``None`` only if prepare() skipped enrichment
    # (it does not — enrichment is mandatory and fail-closed).
    governance: TaskGovernanceStatus | None = None


class ReviewRunnerStub:
    """Accept verified review sessions without invoking reviewer models."""

    pending_status = "pending_model_runner"

    def __init__(self, session_builder: ReviewSessionBuilder | None = None) -> None:
        self.session_builder = session_builder or ReviewSessionBuilder()

    def prepare(self, session: ReviewSessionEnvelope | Path | str) -> ReviewRunnerResult:
        envelope = (
            self.session_builder.load(session)
            if not isinstance(session, ReviewSessionEnvelope)
            else session
        )
        self.session_builder.verify(envelope)
        document = envelope.document
        assignments = document.get("assignments") or []
        if not assignments:
            raise ReviewRunnerError("Review session has no assignments")

        task_id = str(document["task_id"])
        # Observational governance enrichment: read authoritative governance
        # truth through the public consumer. Integrity failures propagate as
        # GovernanceIntegrityError (fail-closed); they are NOT downgraded to a
        # business-state miss. This call grants no execution authority.
        governance = get_task_governance_status(task_id)

        return ReviewRunnerResult(
            status=self.pending_status,
            review_session_id=str(document["review_session_id"]),
            task_id=task_id,
            evidence_package_id=str(document["evidence_package_id"]),
            assignment_count=len(assignments),
            reason="Model execution is not authorized in this phase",
            governance=governance,
        )
