"""Non-executing reviewer runner interface for Hermes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

        return ReviewRunnerResult(
            status=self.pending_status,
            review_session_id=str(document["review_session_id"]),
            task_id=str(document["task_id"]),
            evidence_package_id=str(document["evidence_package_id"]),
            assignment_count=len(assignments),
            reason="Model execution is not authorized in this phase",
        )
