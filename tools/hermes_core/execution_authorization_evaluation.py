"""Execution-authorization evaluation contracts (EA-3I.1, pure/read-only).

This module defines the *authority-evaluation* half of the EA-3I.1 slice. It
evaluates whether a persisted ``ExecutionAuthorizationRequest`` is eligible for
future authorization under a resolved ``ExecutionAuthorizationPolicy`` and an
actor context. It is PRE-CAPABILITY:

- it never builds or persists an ``ExecutionAuthorization``;
- it never builds or persists a GRANTED/DENIED ``ExecutionAuthorizationDecision``;
- it never calls ``record_granted_decision_and_authorization(...)`` (EA-3B);
- it never generates nonce / issued_at / expires_at for authority;
- it never creates a claim, attempt, or worker behavior.

The evaluator is deterministic: identical immutable
(request, actor_context, policy) inputs produce an identical result. No
wall-clock, randomness, or mutable global policy state is consulted.

ACCEPTED != EXECUTION AUTHORIZATION is preserved: acceptance is a
read-only prerequisite checked by the caller; a passing evaluation is only an
eligibility opinion, never an authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .execution_authorization import (
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationRequest,
    ExecutionAuthorizationScope,
)
from .execution_authorization_policy import (
    ExecutionAuthorizationPolicy,
    ExecutionAuthorizationPolicyDecision,
    ExecutionAuthorizationPolicyNotFoundError,
    ExecutionAuthorizationPolicyVersionError,
    resolve_policy,
)
from .acceptance_artifact import AcceptanceArtifact

# --------------------------------------------------------------------------- #
# Actor-context + evaluation errors
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationEvaluationError(ValueError):
    """A non-eligibility failure (corrupt input, mismatch, missing prerequisite).

    Errors are distinct from a DENY decision: a DENY is a valid policy refusing
    a well-formed request; an error means the evaluation could not complete.
    Errors must NOT be downgraded to DENY.
    """


class ExecutionAuthorizationActorAuthenticationError(ExecutionAuthorizationEvaluationError):
    """The actor presented no acceptable authentication evidence."""


class ExecutionAuthorizationActorAuthorityError(ExecutionAuthorizationEvaluationError):
    """The actor's authority role is unknown or unrecognized for the policy."""


# --------------------------------------------------------------------------- #
# Actor context (identity / authentication / authority, kept separate)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionAuthorizationActorContext:
    """Non-secret actor context for evaluation.

    Carries identity, authentication evidence presence, and the authority role.
    It does NOT carry credentials (password/key/token/secret); only structural
    and provenance identifiers (a reference to verified session / IdP assertion
    / operator-console session / service-identity assertion).
    """

    actor_id: str
    actor_type: ExecutionAuthorizationActorType
    authority_role: str
    authentication_evidence_present: bool
    authentication_reference: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise ExecutionAuthorizationEvaluationError("actor_id must be non-empty")
        if not isinstance(self.actor_type, ExecutionAuthorizationActorType):
            raise ExecutionAuthorizationEvaluationError("actor_type must be a valid ExecutionAuthorizationActorType")
        if not self.authority_role:
            raise ExecutionAuthorizationEvaluationError("authority_role must be non-empty")


# --------------------------------------------------------------------------- #
# Structured result (no bare bool; no capability-bearing identifiers)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionAuthorizationEvaluationResult:
    """Audit-rich evaluation result. Contains enough data to explain a future
    decision, but NO capability-bearing identifiers (no authorization_id,
    decision_id, nonce, issued_at)."""

    request_id: str
    request_hash: str
    actor_id: str
    actor_type: ExecutionAuthorizationActorType
    authority_role: str
    policy_id: str
    policy_version: str
    outcome: ExecutionAuthorizationPolicyDecision
    reason: str
    constrained_scope: ExecutionAuthorizationScope
    requires_human: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionAuthorizationPolicyEvaluation:
    """The evaluation returned by ``evaluate_execution_authorization_policy``.

    Wraps the structured result together with the resolved policy reference so
    a future capability-bearing step can bind the exact policy that was applied.
    """

    result: ExecutionAuthorizationEvaluationResult
    policy: ExecutionAuthorizationPolicy

    @property
    def request_id(self) -> str:
        return self.result.request_id

    @property
    def outcome(self) -> ExecutionAuthorizationPolicyDecision:
        return self.result.outcome


# --------------------------------------------------------------------------- #
# Read-only acceptance prerequisite validation
# --------------------------------------------------------------------------- #


def verify_acceptance_prerequisite(
    request: ExecutionAuthorizationRequest,
    acceptance: AcceptanceArtifact,
) -> None:
    """Read-only check that the request's governance acceptance binding matches
    the supplied AcceptanceArtifact.

    This is a prerequisite check only. ACCEPTED != authorized: a matching,
    accepted artifact satisfies a prerequisite but grants nothing. The function
    does not open governance.db, does not mutate state, and accepts an
    already-loaded ``AcceptanceArtifact``.
    """
    if not isinstance(acceptance, AcceptanceArtifact):
        raise ExecutionAuthorizationEvaluationError("acceptance must be an AcceptanceArtifact")
    if request.accepted_governance_artifact_id != acceptance.acceptance_id:
        raise ExecutionAuthorizationEvaluationError(
            f"request accepted_governance_artifact_id {request.accepted_governance_artifact_id} "
            f"!= acceptance acceptance_id {acceptance.acceptance_id}"
        )
    if request.accepted_governance_hash != acceptance.acceptance_sha256:
        raise ExecutionAuthorizationEvaluationError(
            f"request accepted_governance_hash {request.accepted_governance_hash} "
            f"!= acceptance acceptance_sha256 {acceptance.acceptance_sha256}"
        )
    if request.task_id != acceptance.task_id:
        raise ExecutionAuthorizationEvaluationError(
            f"request task_id {request.task_id} != acceptance task_id {acceptance.task_id}"
        )
    if not acceptance.is_accepted:
        raise ExecutionAuthorizationEvaluationError(
            "acceptance disposition is not ACCEPTED; execution authorization "
            "prerequisite not satisfied"
        )


# --------------------------------------------------------------------------- #
# Scope constraint (never widen)
# --------------------------------------------------------------------------- #


def constrain_scope(
    requested: ExecutionAuthorizationScope, policy: ExecutionAuthorizationPolicy
) -> ExecutionAuthorizationScope:
    """Return a scope that is <= requested on every authority dimension.

    attempt_limit and max_runtime_seconds are capped at the policy ceilings
    (never increased). input_hash is preserved verbatim. operation and
    worker_class are passed through (eligibility is decided by the evaluator,
    not here); this helper only enforces the no-widening invariant.
    """
    attempt_limit = min(requested.attempt_limit, policy.max_attempt_limit)
    if policy.max_runtime_seconds is None:
        max_rt = requested.max_runtime_seconds
    elif requested.max_runtime_seconds is None:
        max_rt = policy.max_runtime_seconds
    else:
        max_rt = min(requested.max_runtime_seconds, policy.max_runtime_seconds)
    return ExecutionAuthorizationScope(
        operation=requested.operation,
        worker_class=requested.worker_class,
        input_hash=requested.input_hash,
        attempt_limit=attempt_limit,
        max_runtime_seconds=max_rt,
    )


# --------------------------------------------------------------------------- #
# Pure evaluator
# --------------------------------------------------------------------------- #


def evaluate_execution_authorization_policy(
    *,
    request: ExecutionAuthorizationRequest,
    actor_context: ExecutionAuthorizationActorContext,
    policy_ref: Optional[ExecutionAuthorizationPolicyRef] = None,
    policy: Optional[ExecutionAuthorizationPolicy] = None,
) -> ExecutionAuthorizationPolicyEvaluation:
    """Pure, read-only policy + authority evaluation.

    Resolution: if ``policy`` is supplied it is used directly; otherwise
    ``policy_ref`` (or ``request.authorization_policy``) is resolved
    deterministically. The request carries a policy ref, but it is treated as
    an expected/requested reference that MUST be validated against
    deterministic resolution, never blindly trusted.

    No DB writes. No EA-3B atomic-grant call. No authority created.
    """
    if policy is None:
        ref = policy_ref or request.authorization_policy
        policy = resolve_policy(ref.policy_id, ref.policy_version)

    req_scope = request.requested_scope

    # 1) Authentication evidence is a prerequisite (not a policy DENY).
    if not actor_context.authentication_evidence_present:
        raise ExecutionAuthorizationActorAuthenticationError(
            f"actor {actor_context.actor_id} presented no acceptable "
            f"authentication evidence"
        )

    # 2) SYSTEM must never grant execution authority by default. This is an
    #    eligibility posture, not a role-recognition question: handle it before
    #    the role check so SYSTEM is unconditionally denied regardless of role.
    if actor_context.actor_type == ExecutionAuthorizationActorType.SYSTEM:
        return _decide(
            request, actor_context, policy,
            ExecutionAuthorizationPolicyDecision.DENY,
            "SYSTEM actor is never eligible to grant execution authority by default",
            constrained_scope=constrain_scope(req_scope, policy),
        )

    # 3) Authority-role recognition (not a policy DENY).
    if not actor_context.authority_role:
        raise ExecutionAuthorizationActorAuthorityError("authority_role is empty")
    if not policy.allows_role(actor_context.actor_type, actor_context.authority_role):
        raise ExecutionAuthorizationActorAuthorityError(
            f"actor type {actor_context.actor_type.value} role "
            f"{actor_context.authority_role} is not authorized for policy "
            f"{policy.policy_id} v{policy.policy_version}"
        )

    # 4) Operation known? (fail closed)
    if req_scope.operation not in policy.known_operations:
        return _decide(
            request, actor_context, policy,
            ExecutionAuthorizationPolicyDecision.DENY,
            "unknown operation",
            constrained_scope=constrain_scope(req_scope, policy),
        )

    # 5) worker_class handling (None = deferred/unresolved -> REQUIRES_HUMAN
    #    unless the policy explicitly permits deferred; unknown -> fail closed).
    wc = req_scope.worker_class
    if wc is None:
        if None in policy.known_worker_classes:
            # Deferred worker selection is recognized but not unrestricted;
            # explicit human decision is required to bind a concrete worker.
            return _decide(
                request, actor_context, policy,
                ExecutionAuthorizationPolicyDecision.REQUIRES_HUMAN,
                "worker_class unresolved/deferred requires human decision",
                constrained_scope=constrain_scope(req_scope, policy),
            )
        return _decide(
            request, actor_context, policy,
            ExecutionAuthorizationPolicyDecision.DENY,
            "worker_class None and policy does not permit deferred worker selection",
            constrained_scope=constrain_scope(req_scope, policy),
        )
    if wc not in policy.known_worker_classes:
        return _decide(
            request, actor_context, policy,
            ExecutionAuthorizationPolicyDecision.DENY,
            f"unknown worker_class {wc}",
            constrained_scope=constrain_scope(req_scope, policy),
        )

    # 5) Actor-type authority posture.
    outcome: ExecutionAuthorizationPolicyDecision
    reason: str
    if actor_context.actor_type == ExecutionAuthorizationActorType.SYSTEM:
        # SYSTEM must not grant execution authority by default.
        outcome = ExecutionAuthorizationPolicyDecision.DENY
        reason = "SYSTEM actor is never eligible to grant execution authority by default"
    elif actor_context.actor_type == ExecutionAuthorizationActorType.POLICY_SERVICE:
        # Conservative default: no auto-authorizable scopes unless enumerated.
        if policy.auto_scope_for(req_scope.operation, wc):
            outcome = ExecutionAuthorizationPolicyDecision.ALLOW
            reason = "POLICY_SERVICE enumerated auto-scope matches request"
        else:
            outcome = ExecutionAuthorizationPolicyDecision.REQUIRES_HUMAN
            reason = "POLICY_SERVICE requires explicit human decision (no enumerated auto-scope)"
    else:  # HUMAN
        # Authenticated + recognized role + known op/worker -> ALLOW by default.
        # A policy may still carry explicit denials via allowed_roles; if the
        # role passed step 2, it is authorized for this policy.
        outcome = ExecutionAuthorizationPolicyDecision.ALLOW
        reason = "authenticated HUMAN with authorized role and known operation/worker is eligible"

    # 6) Scope narrowing (never widen); if a constraint changed the requested
    #    scope, a human must confirm the narrowed grant.
    constrained = constrain_scope(req_scope, policy)
    if (constrained.attempt_limit != req_scope.attempt_limit
            or constrained.max_runtime_seconds != req_scope.max_runtime_seconds):
        if outcome == ExecutionAuthorizationPolicyDecision.ALLOW:
            outcome = ExecutionAuthorizationPolicyDecision.REQUIRES_HUMAN
            reason = "requested authority constrained by policy ceiling; human confirmation required"

    return _decide(request, actor_context, policy, outcome, reason, constrained_scope=constrained)


def _decide(
    request: ExecutionAuthorizationRequest,
    actor_context: ExecutionAuthorizationActorContext,
    policy: ExecutionAuthorizationPolicy,
    outcome: ExecutionAuthorizationPolicyDecision,
    reason: str,
    constrained_scope: ExecutionAuthorizationScope,
) -> ExecutionAuthorizationPolicyEvaluation:
    result = ExecutionAuthorizationEvaluationResult(
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        actor_id=actor_context.actor_id,
        actor_type=actor_context.actor_type,
        authority_role=actor_context.authority_role,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        outcome=outcome,
        reason=reason,
        constrained_scope=constrained_scope,
        requires_human=(outcome == ExecutionAuthorizationPolicyDecision.REQUIRES_HUMAN),
    )
    return ExecutionAuthorizationPolicyEvaluation(result=result, policy=policy)
