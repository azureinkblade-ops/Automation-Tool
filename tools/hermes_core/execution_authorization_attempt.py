"""EA-4B: atomic Claim -> ExecutionAttempt consumption.

This milestone introduces the first durable consumption of a valid ExecutionClaim
into an ExecutionAttempt. It establishes:

    Durable ExecutionClaim
        ↓
    replay check (existing attempt returned for same claim + claimant)
        ↓
    claim existence + integrity + not expired
        ↓
    authorization existence + integrity
        ↓
    attempt limit enforcement
        ↓
    next attempt number assignment
        ↓
    must_start_by derivation (bounded by claim expiry)
        ↓
    atomic Attempt persistence + ATTEMPT_RECORDED
        ↓
    ExecutionAttempt persisted
        ↓
    STOP

EXECUTION_ATTEMPT_RECORDED != EXECUTING: a persisted Attempt means only that
a valid Claim has been consumed into a durable pre-execution attempt. It does
NOT mean a worker was selected, launched, or that execution has begun.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .execution_authorization import (
    DEFAULT_MAX_CLAIM_LIFETIME_SECONDS,
    ExecutionAuthorizationPolicyRef,
    ExecutionAttempt,
    ExecutionAttemptActor,
    ExecutionAttemptStatus,
    ExecutionClaim,
    ExecutionClaimant,
    build_execution_attempt,
)
from .execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationStoreError,
)
from .sqlite_execution_authorization_store import SQLiteExecutionAuthorizationStore


class ExecutionAttemptError(ExecutionAuthorizationStoreError):
    """Base class for attempt-consumption errors."""


class ExecutionAttemptClaimExpiredError(ExecutionAttemptError):
    """Raised when the Claim has expired at attempt-creation time."""


class ExecutionAttemptLimitError(ExecutionAttemptError):
    """Raised when the attempt ceiling has been exhausted."""


class ExecutionAttemptConflictError(ExecutionAttemptError):
    """Raised when an attempt conflicts with an existing durable attempt."""


class ExecutionAttemptLineageError(ExecutionAttemptError):
    """Raised when attempt lineage does not match its Authorization/Claim."""


class ExecutionAttemptClockError(ExecutionAttemptError):
    """Clock/timeout failure during attempt; fail closed, never a denial."""


class ExecutionAttemptResult:
    """Structured result of an attempt operation. No bool-only API."""

    __slots__ = (
        "authorization_id",
        "claim_id",
        "attempt_id",
        "attempt_hash",
        "attempt_number",
        "attempt_recorded_at",
        "must_start_by",
        "claimant_id",
        "persisted",
        "replayed",
        "reason",
    )

    def __init__(
        self,
        *,
        authorization_id: str,
        claim_id: str,
        attempt_id: Optional[str],
        attempt_hash: Optional[str],
        attempt_number: int,
        attempt_recorded_at: Optional[str],
        must_start_by: Optional[str],
        claimant_id: str,
        persisted: bool,
        replayed: bool,
        reason: str,
    ) -> None:
        self.authorization_id = authorization_id
        self.claim_id = claim_id
        self.attempt_id = attempt_id
        self.attempt_hash = attempt_hash
        self.attempt_number = attempt_number
        self.attempt_recorded_at = attempt_recorded_at
        self.must_start_by = must_start_by
        self.claimant_id = claimant_id
        self.persisted = persisted
        self.replayed = replayed
        self.reason = reason


def _now_utc(clock: Optional[Callable[[], str]] = None) -> str:
    """Absolute UTC RFC3339/ISO-8601 timestamp ending in 'Z'.

    Uses the injected ``clock`` provider (deterministic tests) or the real UTC
    wall clock. Any failure fails closed as ExecutionAttemptClockError.
    """
    try:
        if clock is not None:
            value = clock()
        else:
            value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception as exc:  # noqa: BLE001 - fail closed on any clock fault
        raise ExecutionAttemptClockError(
            f"attempt clock unavailable: {exc}"
        ) from exc
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ExecutionAttemptClockError(
            f"attempt clock must yield an absolute UTC timestamp ending in 'Z', "
            f"got {value!r}"
        )
    return value


def consume_claim_into_attempt(
    *,
    store: SQLiteExecutionAuthorizationStore,
    authorization_id: str,
    claim_id: str,
    claimant: ExecutionAttemptActor,
    must_start_within_seconds: Optional[int] = None,
    clock: Optional[Callable[[], str]] = None,
) -> ExecutionAttemptResult:
    """Consume a valid ExecutionClaim into a durable ExecutionAttempt.

    Enforces: claim exists + integrity valid + not expired at attempt time;
    authorization exists + integrity valid; attempt limit derived from the
    persisted Authorization scope (caller cannot raise the ceiling); monotonic
    attempt numbering; bounded must_start_by; atomic persistence as a single
    BEGIN IMMEDIATE transaction. Never launches/consumes work beyond the
    durable attempt record.
    """
    if not isinstance(claimant, ExecutionAttemptActor):
        raise ExecutionAttemptError("claimant must be an ExecutionAttemptActor")
    if not authorization_id:
        raise ExecutionAttemptError("authorization_id is required")
    if not claim_id:
        raise ExecutionAttemptError("claim_id is required")

    # Wrap the entire consume in a single BEGIN IMMEDIATE transaction.
    # This eliminates the TOCTOU race between the read/count and the write.
    # The replay check, limit check, attempt-number assignment, and
    # persistence all happen atomically.
    return store.consume_claim_transaction(
        authorization_id=authorization_id,
        claim_id=claim_id,
        claimant=claimant,
        must_start_within_seconds=must_start_within_seconds,
        clock=clock or _now_utc,
    )
