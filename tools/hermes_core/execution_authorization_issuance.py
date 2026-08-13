"""Capability-bearing execution-authorization issuance (EA-3I.2).

This is the FIRST milestone permitted to create real execution authority. It
orchestrates, in strict order:

    Request (already persisted, hash-verified)
        -> exact AcceptanceArtifact prerequisite (read-only, via governance chain)
        -> actor authentication + authority-role validation
        -> deterministic policy resolution (exact id/version from the Request)
        -> EA-3I.1 policy + authority evaluation
        -> DENY  : persist a terminal DENIED Decision only (no Authorization)
        -> ALLOW : construct matched GRANTED Decision + ExecutionAuthorization
                   and persist atomically via the EA-3B store
        -> REQUIRES_HUMAN : no Decision, no Authorization

`REQUIRES_HUMAN` can never silently become ALLOW. The service STOPS after
durable authorization evidence exists. It does NOT create a claim, attempt,
worker behavior, or execution transition, and it does NOT mutate governance
state (it only reads the exact AcceptanceArtifact through the existing
governance-chain read API).

ACCEPTED != EXECUTION AUTHORIZATION is preserved: acceptance is a read-only
prerequisite; this module mints separate execution authority bound to it.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from .acceptance_artifact import AcceptanceArtifact
from .execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationDecisionOutcome,
    build_execution_authorization,
    build_execution_authorization_decision,
)
from .execution_authorization_evaluation import (
    ExecutionAuthorizationActorContext,
    ExecutionAuthorizationActorAuthenticationError,
    ExecutionAuthorizationActorAuthorityError,
    ExecutionAuthorizationEvaluationError,
    ExecutionAuthorizationPolicyDecision,
    evaluate_execution_authorization_policy,
    verify_acceptance_prerequisite,
)
from .execution_authorization_policy import (
    ExecutionAuthorizationPolicy,
    ExecutionAuthorizationPolicyNotFoundError,
    ExecutionAuthorizationPolicyVersionError,
    resolve_policy,
)
from .execution_authorization_store import ExecutionAuthorizationStore
from .sqlite_governance_store import SQLiteGovernanceStore


# --------------------------------------------------------------------------- #
# Issuance errors (distinct from a DENY decision)
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationIssuanceError(ValueError):
    """Base class for issuance failures (distinct from a DENY policy decision)."""


class ExecutionAuthorizationRequestNotFoundError(ExecutionAuthorizationIssuanceError):
    """No persisted Request exists for the requested request_id."""


class ExecutionAuthorizationAcceptanceError(ExecutionAuthorizationIssuanceError):
    """The bound AcceptanceArtifact is missing or fails exact prerequisite."""


class ExecutionAuthorizationClockError(ExecutionAuthorizationIssuanceError):
    """The issuance clock is unavailable, malformed, non-UTC, or rolled back.

    Clock failure is never translated into a DENY; it fails closed with no
    Decision and no Authorization persisted.
    """


class ExecutionAuthorizationConflictError(ExecutionAuthorizationIssuanceError):
    """Conflicting terminal evidence already exists for the Request."""


# --------------------------------------------------------------------------- #
# Issuance outcome vocabulary
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationIssuanceOutcome(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"


# Conservative default lifetime when a policy does not pin one.
DEFAULT_MAX_LIFETIME_SECONDS = 3600


# --------------------------------------------------------------------------- #
# Structured issuance result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionAuthorizationIssuanceResult:
    """Audit-rich issuance result. No execution handle; no mutable runtime state."""

    request_id: str
    request_hash: str
    evaluation_outcome: ExecutionAuthorizationIssuanceOutcome
    decision_id: Optional[str]
    decision_hash: Optional[str]
    authorization_id: Optional[str]
    authorization_hash: Optional[str]
    persisted: bool
    reason: str


# --------------------------------------------------------------------------- #
# Clock seam
# --------------------------------------------------------------------------- #


def _now_utc(clock: Optional[Callable[[], str]] = None) -> str:
    """Return an absolute UTC RFC3339/ISO-8601 timestamp ending in 'Z'.

    Uses the injected ``clock`` provider (deterministic tests) or the real
    UTC wall clock. Any failure (exception, non-string, non-'Z' value) fails
    closed as an ExecutionAuthorizationClockError — never a DENY.
    """
    try:
        if clock is not None:
            value = clock()
        else:
            value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception as exc:  # noqa: BLE001 - fail closed on any clock fault
        raise ExecutionAuthorizationClockError(f"issuance clock unavailable: {exc}") from exc
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ExecutionAuthorizationClockError(
            f"issuance clock must yield an absolute UTC timestamp ending in 'Z', got {value!r}"
        )
    return value


def _expires_at(issued_at: str, lifetime_seconds: int) -> str:
    dt = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    exp = dt + timedelta(seconds=lifetime_seconds)
    return exp.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# Actor context -> decision actor
# --------------------------------------------------------------------------- #


def _deciding_actor(ctx: ExecutionAuthorizationActorContext) -> ExecutionAuthorizationActor:
    """The Decision must record the ACTUAL deciding actor, never the
    requesting actor substituted silently."""
    return ExecutionAuthorizationActor(
        actor_id=ctx.actor_id,
        actor_type=ctx.actor_type,
        authority_role=ctx.authority_role,
        authentication_context=ctx.authentication_reference,
    )


# --------------------------------------------------------------------------- #
# Issuance orchestration
# --------------------------------------------------------------------------- #


def issue_execution_authorization(
    *,
    store: ExecutionAuthorizationStore,
    governance_store: SQLiteGovernanceStore,
    request_id: str,
    actor_context: ExecutionAuthorizationActorContext,
    clock: Optional[Callable[[], str]] = None,
) -> ExecutionAuthorizationIssuanceResult:
    """Capability-bearing issuance for one already-persisted Request.

    Pure orchestration over existing contracts; it does not duplicate policy
    logic, does not touch governance state (read-only acceptance lookup), and
    persists only through the EA-3B store's safe public APIs.

    Errors (not DENY) are raised for: missing request, corrupt request hash,
    missing/non-accepted/mismatched acceptance, actor auth/authority failure,
    unknown/unsupported policy, and clock failure.
    """
    # 1) Request prerequisite (already-persisted only).
    request = store.get_request(request_id)
    if request is None:
        raise ExecutionAuthorizationRequestNotFoundError(
            f"no persisted ExecutionAuthorizationRequest for {request_id!r}"
        )

    # 2) Request integrity.
    if not request.verify_hash():
        raise ExecutionAuthorizationIssuanceError(
            f"request {request_id} failed hash verification (corrupt)"
        )

    # 3) Replay: existing terminal evidence checked before any new issuance.
    existing = store.get_decision_for_request(request_id)
    if existing is not None:
        if existing.outcome is ExecutionAuthorizationDecisionOutcome.GRANTED:
            auth = store.get_authorization_for_request(request_id)
            return ExecutionAuthorizationIssuanceResult(
                request_id=request_id,
                request_hash=request.artifact_hash,
                evaluation_outcome=ExecutionAuthorizationIssuanceOutcome.AUTHORIZED,
                decision_id=existing.decision_id,
                decision_hash=existing.artifact_hash,
                authorization_id=auth.authorization_id if auth else None,
                authorization_hash=auth.artifact_hash if auth else None,
                persisted=True,
                reason="existing terminal GRANTED authorization returned (idempotent replay)",
            )
        # DENIED terminal: never re-decide; return existing denial.
        return ExecutionAuthorizationIssuanceResult(
            request_id=request_id,
            request_hash=request.artifact_hash,
            evaluation_outcome=ExecutionAuthorizationIssuanceOutcome.DENIED,
            decision_id=existing.decision_id,
            decision_hash=existing.artifact_hash,
            authorization_id=None,
            authorization_hash=None,
            persisted=True,
            reason="existing terminal DENIED decision returned (idempotent replay)",
        )

    # 4) Acceptance prerequisite (exact, read-only). Bare task_id equivalence is
    #    insufficient: verify_acceptance_prerequisite checks the exact
    #    acceptance_id / acceptance_sha256 / task_id / is_accepted().
    chain = governance_store.load_task_governance_chain(request.task_id)
    acceptance: Optional[AcceptanceArtifact] = chain.acceptance
    if acceptance is None:
        raise ExecutionAuthorizationAcceptanceError(
            f"no AcceptanceArtifact for task {request.task_id}"
        )
    try:
        verify_acceptance_prerequisite(request, acceptance)
    except ExecutionAuthorizationEvaluationError as exc:
        raise ExecutionAuthorizationAcceptanceError(str(exc)) from exc

    # 5) Actor authentication (prerequisite, not a DENY).
    if not actor_context.authentication_evidence_present:
        raise ExecutionAuthorizationActorAuthenticationError(
            f"actor {actor_context.actor_id} presented no acceptable authentication evidence"
        )

    # 6) Deterministic policy resolution from the REQUEST's exact reference.
    #    No fallback to default/latest; unknown/unsupported -> ERROR.
    try:
        policy = resolve_policy(
            request.authorization_policy.policy_id,
            request.authorization_policy.policy_version,
        )
    except (ExecutionAuthorizationPolicyNotFoundError, ExecutionAuthorizationPolicyVersionError) as exc:
        raise ExecutionAuthorizationIssuanceError(str(exc)) from exc

    # 7) Reuse the EA-3I.1 evaluator (no duplicated policy logic).
    evaluation = evaluate_execution_authorization_policy(
        request=request, actor_context=actor_context, policy=policy
    )
    outcome = evaluation.result.outcome
    deciding_actor = _deciding_actor(actor_context)

    # 8a) DENY -> persist terminal DENIED Decision only (authorization_id None).
    if outcome is ExecutionAuthorizationPolicyDecision.DENY:
        decision = build_execution_authorization_decision(
            request_id=request.request_id,
            request_hash=request.artifact_hash,
            task_id=request.task_id,
            decision_actor=deciding_actor,
            outcome=ExecutionAuthorizationDecisionOutcome.DENIED,
            decision_reason=(
                f"policy {policy.policy_id} v{policy.policy_version}: "
                f"{evaluation.result.reason}"
            ),
            authorization_id=None,
            authorization_policy=request.authorization_policy,
        )
        store.record_decision(decision)
        return ExecutionAuthorizationIssuanceResult(
            request_id=request.request_id,
            request_hash=request.artifact_hash,
            evaluation_outcome=ExecutionAuthorizationIssuanceOutcome.DENIED,
            decision_id=decision.decision_id,
            decision_hash=decision.artifact_hash,
            authorization_id=None,
            authorization_hash=None,
            persisted=True,
            reason=evaluation.result.reason,
        )

    # 8b) REQUIRES_HUMAN -> no Decision, no Authorization. Never silently ALLOW.
    if outcome is not ExecutionAuthorizationPolicyDecision.ALLOW:
        return ExecutionAuthorizationIssuanceResult(
            request_id=request.request_id,
            request_hash=request.artifact_hash,
            evaluation_outcome=ExecutionAuthorizationIssuanceOutcome.REQUIRES_HUMAN,
            decision_id=None,
            decision_hash=None,
            authorization_id=None,
            authorization_hash=None,
            persisted=False,
            reason=evaluation.result.reason,
        )

    # 8c) ALLOW -> construct matched Decision + Authorization, persist atomically.
    # Clock / expiry (fail closed on any clock fault).
    issued_at = _now_utc(clock)
    lifetime = policy.max_authorization_lifetime_seconds or DEFAULT_MAX_LIFETIME_SECONDS
    if not isinstance(lifetime, int) or lifetime <= 0:
        raise ExecutionAuthorizationIssuanceError(
            f"policy {policy.policy_id} v{policy.policy_version} provides no positive "
            f"max_authorization_lifetime_seconds"
        )
    expires_at = _expires_at(issued_at, lifetime)

    # Authorized scope MUST come from the evaluation's constrained scope, never
    # the raw requested scope (never wider).
    constrained = evaluation.result.constrained_scope
    nonce = secrets.token_hex(16)

    # EA-3A acyclic Model A: build the decision first (its authorization_id is
    # excluded from its hash preimage), then the authorization (which binds the
    # decision_id/decision_hash), then realign the decision's authorization_id.
    decision = build_execution_authorization_decision(
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        task_id=request.task_id,
        decision_actor=deciding_actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason=(
            f"policy {policy.policy_id} v{policy.policy_version} ALLOW: "
            f"{evaluation.result.reason}"
        ),
        authorization_id="execution-authorization-pending",
        authorization_policy=request.authorization_policy,
    )
    authorization = build_execution_authorization(
        task_id=request.task_id,
        accepted_governance_artifact_id=request.accepted_governance_artifact_id,
        accepted_governance_hash=request.accepted_governance_hash,
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        authorization_actor=deciding_actor,
        authorized_scope=constrained,
        authorization_reason=(
            f"policy {policy.policy_id} v{policy.policy_version} ALLOW; "
            f"role {actor_context.authority_role}; scope {constrained.operation}/"
            f"{constrained.worker_class}"
        ),
        authorization_policy=request.authorization_policy,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )
    decision = _align_decision_authorization_id(decision, authorization.authorization_id)

    # Single atomic persistence path only (EA-3B). No standalone GRANTED/
    # Authorization calls.
    store.record_granted_decision_and_authorization(decision, authorization)
    return ExecutionAuthorizationIssuanceResult(
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        evaluation_outcome=ExecutionAuthorizationIssuanceOutcome.AUTHORIZED,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        persisted=True,
        reason=evaluation.result.reason,
    )


def _align_decision_authorization_id(decision, authorization_id):
    """Realign the decision's forward-only authorization_id to the (derived)
    authorization id. Safe: authorization_id is excluded from the decision hash
    preimage (EA-3A Model A), so decision.artifact_hash is unaffected and stays
    consistent with the authorization's decision_hash."""
    from dataclasses import replace

    return replace(decision, authorization_id=authorization_id)
