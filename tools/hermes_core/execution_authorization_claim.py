"""EA-4A: capability-bearing ExecutionClaim issuance (atomic persistence).

This is the first milestone permitted to create a durable execution claim. It
orchestrates, in strict order:

    Durable ExecutionAuthorization
        ↓
    replay check (existing claim returned, no new claim)
        ↓
    authorization validity + integrity at claim time
        ↓
    claim-time expiry check (claimed_at < authorization.expires_at)
        ↓
    claim lifetime window (bounded, non-null, claim_expires_at > claimed_at)
        ↓
    atomic claim creation (store handles UNIQUE + ledger)
        ↓
    ExecutionClaim persisted
        ↓
    STOP

CLAIMED != EXECUTING: a persisted Claim means only that a specific claimant
reserved/consumed the Authorization for a future execution attempt. It does NOT
start a process, worker, or command. No ExecutionAttempt, no worker, no
execution runtime is created here.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .execution_authorization import (
    DEFAULT_MAX_CLAIM_LIFETIME_SECONDS,
    ExecutionAuthorizationPolicyRef,
    ExecutionClaim,
    ExecutionClaimant,
)
from .execution_authorization_store import (
    ExecutionAuthorizationConflictError,
    ExecutionAuthorizationStoreError,
)
from .sqlite_execution_authorization_store import SQLiteExecutionAuthorizationStore


class ExecutionAuthorizationClaimError(ExecutionAuthorizationStoreError):
    """Base class for claim-time errors that are NOT a policy DENY."""


class ExecutionAuthorizationClaimConflictError(ExecutionAuthorizationClaimError):
    """An existing Claim already reserves this Authorization."""


class ExecutionAuthorizationClaimClockError(ExecutionAuthorizationClaimError):
    """Clock/timeout failure during claim; fail closed, never a denial."""


class ExecutionClaimResult:
    """Structured result of a claim operation. No bool-only API."""

    __slots__ = (
        "authorization_id",
        "claim_id",
        "claim_hash",
        "claimed_at",
        "claim_expires_at",
        "claimant_id",
        "persisted",
        "replayed",
        "reason",
    )

    def __init__(
        self,
        *,
        authorization_id: str,
        claim_id: Optional[str],
        claim_hash: Optional[str],
        claimed_at: Optional[str],
        claim_expires_at: Optional[str],
        claimant_id: str,
        persisted: bool,
        replayed: bool,
        reason: str,
    ) -> None:
        self.authorization_id = authorization_id
        self.claim_id = claim_id
        self.claim_hash = claim_hash
        self.claimed_at = claimed_at
        self.claim_expires_at = claim_expires_at
        self.claimant_id = claimant_id
        self.persisted = persisted
        self.replayed = replayed
        self.reason = reason


def _now_utc(clock: Optional[Callable[[], str]] = None) -> str:
    """Absolute UTC RFC3339/ISO-8601 timestamp ending in 'Z'.

    Uses the injected ``clock`` provider (deterministic tests) or the real UTC
    wall clock. Any failure fails closed as ExecutionAuthorizationClaimClockError.
    """
    try:
        if clock is not None:
            value = clock()
        else:
            value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception as exc:  # noqa: BLE001 - fail closed on any clock fault
        raise ExecutionAuthorizationClaimClockError(
            f"claim clock unavailable: {exc}"
        ) from exc
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ExecutionAuthorizationClaimClockError(
            f"claim clock must yield an absolute UTC timestamp ending in 'Z', "
            f"got {value!r}"
        )
    return value


def _claim_expires_at(issued_at: str, lifetime_seconds: int) -> str:
    dt = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    exp = dt + timedelta(seconds=lifetime_seconds)
    return exp.isoformat().replace("+00:00", "Z")


def claim_execution_authorization(
    *,
    store: SQLiteExecutionAuthorizationStore,
    authorization_id: str,
    claimant: ExecutionClaimant,
    claim_lifetime_seconds: Optional[int] = None,
    clock: Optional[Callable[[], str]] = None,
) -> ExecutionClaimResult:
    """Create (or return an existing) durable ExecutionClaim for an Authorization.

    Enforces: authorization exists + integrity valid + unexpired at claim time;
    at most one active claim per Authorization (exact replay idempotent for the
    same claimant, CONFLICT for a different claimant); bounded non-null claim
    lifetime; atomic persistence via the store. Never launches/consumes work.
    """
    if not isinstance(claimant, ExecutionClaimant):
        raise ExecutionAuthorizationClaimError("claimant must be an ExecutionClaimant")
    if not authorization_id:
        raise ExecutionAuthorizationClaimError("authorization_id is required")

    # 1) Replay: existing terminal claim checked before any new issuance.
    existing = store.get_claim_for_authorization(authorization_id)
    if existing is not None:
        if existing.claimant == claimant:
            return ExecutionClaimResult(
                authorization_id=authorization_id,
                claim_id=existing.claim_id,
                claim_hash=existing.artifact_hash,
                claimed_at=existing.claimed_at,
                claim_expires_at=existing.claim_expires_at,
                claimant_id=existing.claimant.claimant_id,
                persisted=True,
                replayed=True,
                reason="existing claim returned (idempotent replay)",
            )
        # Different claimant: CONFLICT; do not transfer or mutate ownership.
        raise ExecutionAuthorizationClaimConflictError(
            f"authorization {authorization_id} already claimed by "
            f"{existing.claimant.claimant_id}; conflicting claimant "
            f"{claimant.claimant_id} rejected"
        )

    # 2) Authorization prerequisite (integrity-checked read; no caller trust).
    auth = store.get_authorization(authorization_id)
    if auth is None:
        raise ExecutionAuthorizationClaimError(
            f"claim requires a persisted authorization {authorization_id}; "
            f"no such authorization"
        )
    if not auth.verify_hash():
        raise ExecutionAuthorizationClaimError(
            f"authorization {authorization_id} failed integrity verification"
        )

    # 3) Claim-time expiry: claimed_at must be strictly before auth.expires_at.
    if auth.expires_at is None:
        raise ExecutionAuthorizationClaimError(
            "authorization expires_at is null; claim blocked"
        )
    claimed_at = _now_utc(clock)
    claimed_dt = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
    auth_expires_dt = datetime.fromisoformat(auth.expires_at.replace("Z", "+00:00"))
    if claimed_dt >= auth_expires_dt:
        raise ExecutionAuthorizationClaimError(
            "authorization expired at claim time; claim blocked"
        )

    # 4) Claim lifetime window (bounded, non-null, > claimed_at).
    lifetime = claim_lifetime_seconds or DEFAULT_MAX_CLAIM_LIFETIME_SECONDS
    if not isinstance(lifetime, int) or lifetime <= 0:
        raise ExecutionAuthorizationClaimError(
            f"claim lifetime must be a positive integer seconds, got {lifetime!r}"
        )
    claim_expires_at = _claim_expires_at(claimed_at, lifetime)
    expires_dt = datetime.fromisoformat(claim_expires_at.replace("Z", "+00:00"))
    if expires_dt <= claimed_dt:
        raise ExecutionAuthorizationClaimClockError(
            "claim expiry must be strictly after claim time"
        )

    # 5) Build the immutable Claim, bound to the exact Authorization lineage.
    claim = ExecutionClaim(
        claim_id="",  # placeholder; build_execution_claim derives it
        authorization_id=auth.authorization_id,
        authorization_hash=auth.artifact_hash,
        request_id=auth.request_id,
        request_hash=auth.request_hash,
        decision_id=auth.decision_id,
        decision_hash=auth.decision_hash,
        task_id=auth.task_id,
        claimant=claimant,
        claimed_at=claimed_at,
        claim_expires_at=claim_expires_at,
        authorization_policy=auth.authorization_policy,
        claim_reason=(
            f"claim by {claimant.claimant_id} ({claimant.claimant_type}) for "
            f"authorization {auth.authorization_id}"
        ),
        artifact_version="4",
        artifact_hash="",  # placeholder; build_execution_claim derives it
    )
    # Rebuild via the domain builder to derive claim_id + artifact_hash.
    from .execution_authorization import build_execution_claim

    claim = build_execution_claim(
        authorization_id=claim.authorization_id,
        authorization_hash=claim.authorization_hash,
        request_id=claim.request_id,
        request_hash=claim.request_hash,
        decision_id=claim.decision_id,
        decision_hash=claim.decision_hash,
        task_id=claim.task_id,
        claimant=claim.claimant,
        claimed_at=claim.claimed_at,
        claim_expires_at=claim.claim_expires_at,
        authorization_policy=claim.authorization_policy,
        claim_reason=claim.claim_reason,
        artifact_version=claim.artifact_version,
    )

    # 6) Atomic, concurrency-safe persistence. try_claim_* converts a lost
    #    UNIQUE race (another connection committed first) into the correct
    #    domain outcome: idempotent for a matching claim, CONFLICT otherwise.
    won, winning = store.try_claim_authorization_atomically(
        authorization_id, claim, clock=clock
    )
    if not won:
        return ExecutionClaimResult(
            authorization_id=authorization_id,
            claim_id=claim.claim_id,
            claim_hash=claim.artifact_hash,
            claimed_at=claim.claimed_at,
            claim_expires_at=claim.claim_expires_at,
            claimant_id=claim.claimant.claimant_id,
            persisted=True,
            replayed=False,
            reason="ExecutionClaim persisted",
        )
    # Lost the race but a claim already exists: first-writer-wins semantics.
    existing = winning
    if existing.claimant == claim.claimant:
        return ExecutionClaimResult(
            authorization_id=authorization_id,
            claim_id=existing.claim_id,
            claim_hash=existing.artifact_hash,
            claimed_at=existing.claimed_at,
            claim_expires_at=existing.claim_expires_at,
            claimant_id=existing.claimant.claimant_id,
            persisted=True,
            replayed=True,
            reason="existing claim returned (concurrent first-writer-wins)",
        )
    # Different claimant won the race: do not transfer or mutate ownership.
    raise ExecutionAuthorizationClaimConflictError(
        f"authorization {authorization_id} already claimed by "
        f"{existing.claimant.claimant_id}; conflicting concurrent claimant "
        f"{claim.claimant.claimant_id} rejected"
    )
