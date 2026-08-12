"""Deterministic Hermes governance state transition validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .schemas import SchemaCatalog, SchemaValidationError


class StateTransitionError(ValueError):
    """Raised when a Hermes state transition is not allowed."""


STATES = {
    "DRAFT",
    "READY_FOR_REVIEW",
    "UNDER_REVIEW",
    "CONSENSUS_CALCULATED",
    "ACCEPTED",
    "REJECTED",
    "INCONCLUSIVE",
    "AWAITING_EXECUTION_AUTHORIZATION",
    "AUTHORIZED",
    "EXECUTING",
    "VALIDATION_PENDING",
    "VALIDATED",
    "FAILED",
    "CLOSED",
}

ALLOWED_TRANSITIONS = {
    ("DRAFT", "READY_FOR_REVIEW"),
    ("READY_FOR_REVIEW", "UNDER_REVIEW"),
    ("UNDER_REVIEW", "CONSENSUS_CALCULATED"),
    ("CONSENSUS_CALCULATED", "ACCEPTED"),
    ("CONSENSUS_CALCULATED", "REJECTED"),
    ("CONSENSUS_CALCULATED", "INCONCLUSIVE"),
    ("ACCEPTED", "AWAITING_EXECUTION_AUTHORIZATION"),
    ("AWAITING_EXECUTION_AUTHORIZATION", "AUTHORIZED"),
    ("AUTHORIZED", "EXECUTING"),
    ("EXECUTING", "VALIDATION_PENDING"),
    ("EXECUTING", "FAILED"),
    ("VALIDATION_PENDING", "VALIDATED"),
    ("VALIDATION_PENDING", "FAILED"),
    ("REJECTED", "CLOSED"),
    ("INCONCLUSIVE", "CLOSED"),
    ("VALIDATED", "CLOSED"),
    ("FAILED", "CLOSED"),
}

PROHIBITED_TRANSITIONS = {
    ("ACCEPTED", "AUTHORIZED"),
    ("ACCEPTED", "EXECUTING"),
    ("CONSENSUS_CALCULATED", "AUTHORIZED"),
    ("UNDER_REVIEW", "AUTHORIZED"),
    ("READY_FOR_REVIEW", "EXECUTING"),
    ("DRAFT", "EXECUTING"),
    ("EXECUTING", "ACCEPTED"),
    ("VALIDATED", "AUTHORIZED"),
}


@dataclass(frozen=True)
class ArtifactBundle:
    task: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    reviews: list[dict[str, Any]] = field(default_factory=list)
    consensus: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    authorization: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    event_parent_ref: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class TransitionResult:
    from_state: str
    to_state: str
    accepted: bool
    reason: str


def validate_transition(
    from_state: str,
    to_state: str,
    artifacts: ArtifactBundle,
    catalog: SchemaCatalog,
) -> TransitionResult:
    try:
        _validate_known_state(from_state)
        _validate_known_state(to_state)

        if (from_state, to_state) in PROHIBITED_TRANSITIONS:
            raise StateTransitionError(f"Transition {from_state} -> {to_state} is prohibited")
        if (from_state, to_state) not in ALLOWED_TRANSITIONS:
            raise StateTransitionError(f"Transition {from_state} -> {to_state} is not documented")

        _validate_parent_reference(artifacts)

        if to_state == "READY_FOR_REVIEW":
            _require_task_scope(artifacts, catalog)
        elif to_state == "UNDER_REVIEW":
            _require_evidence(artifacts, catalog)
        elif to_state == "CONSENSUS_CALCULATED":
            _require_reviews(artifacts, catalog)
        elif to_state in {"ACCEPTED", "REJECTED", "INCONCLUSIVE"}:
            _require_consensus_for_state(to_state, artifacts, catalog)
        elif to_state == "AWAITING_EXECUTION_AUTHORIZATION":
            _require_acceptance(artifacts, catalog)
        elif to_state == "AUTHORIZED":
            _require_authorization(artifacts, catalog)
        elif to_state == "EXECUTING":
            _require_execution_authority(artifacts, catalog)
        elif to_state in {"VALIDATION_PENDING", "VALIDATED"}:
            _require_execution_record(artifacts, catalog)
    except SchemaValidationError as exc:
        raise StateTransitionError(str(exc)) from exc

    return TransitionResult(
        from_state=from_state,
        to_state=to_state,
        accepted=True,
        reason="transition accepted",
    )


def _validate_known_state(state: str) -> None:
    if state not in STATES:
        raise StateTransitionError(f"Unknown state: {state}")


def _validate_parent_reference(artifacts: ArtifactBundle) -> None:
    if not artifacts.event_parent_ref:
        raise StateTransitionError("Transition requires a parent event or artifact reference")


def _require_task_scope(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    if not artifacts.task:
        raise StateTransitionError("Task artifact is required")
    catalog.validate("hermes.task", artifacts.task)


def _require_evidence(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    if not artifacts.evidence:
        raise StateTransitionError("Frozen evidence artifact is required")
    catalog.validate("hermes.evidence", artifacts.evidence)


def _require_reviews(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    if not artifacts.reviews:
        raise StateTransitionError("At least one review artifact is required")
    for review in artifacts.reviews:
        catalog.validate("hermes.review", review)
        authority = review.get("authority", {})
        if authority.get("can_modify_state") is not False:
            raise StateTransitionError("Review artifacts cannot modify governance state")
        if authority.get("can_authorize_execution") is not False:
            raise StateTransitionError("Review artifacts cannot authorize execution")


def _require_consensus_for_state(
    to_state: str,
    artifacts: ArtifactBundle,
    catalog: SchemaCatalog,
) -> None:
    if not artifacts.consensus:
        raise StateTransitionError("Consensus artifact is required")
    catalog.validate("hermes.consensus", artifacts.consensus)
    result = artifacts.consensus.get("result")
    expected = {
        "ACCEPTED": {"ACCEPTED"},
        "REJECTED": {"REJECTED"},
        "INCONCLUSIVE": {"INCONCLUSIVE", "ESCALATED", "BLOCKED"},
    }[to_state]
    if result not in expected:
        raise StateTransitionError(f"Consensus result {result!r} cannot transition to {to_state}")
    authority = artifacts.consensus.get("authority", {})
    if authority.get("can_authorize_execution") is not False:
        raise StateTransitionError("Consensus artifacts cannot authorize execution")


def _require_acceptance(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    if not artifacts.acceptance:
        raise StateTransitionError("Acceptance artifact is required")
    catalog.validate("hermes.acceptance", artifacts.acceptance)
    authority = artifacts.acceptance.get("authority", {})
    if authority.get("can_authorize_execution") is not False:
        raise StateTransitionError("Acceptance cannot authorize execution")
    if authority.get("requires_separate_authorization") is not True:
        raise StateTransitionError("Acceptance must require separate authorization")


def _require_authorization(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    _require_acceptance(artifacts, catalog)
    if not artifacts.authorization:
        raise StateTransitionError("Authorization artifact is required")
    catalog.validate("hermes.authorization", artifacts.authorization)
    expected_hash = artifacts.acceptance["acceptance_sha256"]
    parent_hash = artifacts.authorization.get("parent_acceptance_sha256")
    if parent_hash != expected_hash:
        raise StateTransitionError("Authorization must reference the parent acceptance hash")
    _validate_not_expired(artifacts.authorization, artifacts.now)


def _require_execution_authority(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    _require_authorization(artifacts, catalog)
    if artifacts.execution:
        catalog.validate("hermes.execution", artifacts.execution)


def _require_execution_record(artifacts: ArtifactBundle, catalog: SchemaCatalog) -> None:
    if not artifacts.execution:
        raise StateTransitionError("Execution artifact is required")
    catalog.validate("hermes.execution", artifacts.execution)


def _validate_not_expired(authorization: dict[str, Any], now: datetime | None) -> None:
    expires_raw = authorization.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaValidationError("authorization.expires_at must be an ISO date-time") from exc
    compare_at = now or datetime.now(timezone.utc)
    if compare_at.tzinfo is None:
        compare_at = compare_at.replace(tzinfo=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= compare_at:
        raise StateTransitionError("Authorization artifact is expired")
