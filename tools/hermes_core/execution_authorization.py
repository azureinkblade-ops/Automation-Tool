"""Immutable domain model for Hermes execution authorization (EA-1 + EA-4A + EA-4B).

This module defines the *structural* domain artifacts only. It does NOT:

* persist anything (no ``execution_authority.db`` / ``SQLiteExecutionAuthorizationStore``);
* issue, consume, or revoke authorizations (no issuance service);
* implement ``ExecutionAttempt`` consumption or claim-consumption services;
* route, launch, enqueue, or dispatch workers;
* introduce execution state transitions (``AWAITING_EXECUTION_AUTHORIZATION``,
  ``AUTHORIZED_FOR_EXECUTION``, ``EXECUTING``).

ACCEPTED != EXECUTION AUTHORIZATION: an ``ExecutionAuthorization`` is a
structured, hash-verifiable *representation* of an authorization decision. It
grants nothing on its own and no production code consumes it yet. The future
issuance service (EA-3) is the only component permitted to create real
authority, and it does not exist in this milestone (EA-3I).

Design source of truth:
    docs/architecture/hermes-execution-authorization-handoff.md
    docs/architecture/decisions/ADR-0013-execution-authority-separate-from-governance.md
    docs/architecture/decisions/ADR-0004-acceptance-vs-execution.md

Conventions follow the existing ``AcceptanceArtifact`` pattern:
``(str, Enum)`` actor/outcome enums, ``@dataclass(frozen=True)`` immutability,
ID derived from a canonical preimage, ``artifact_hash = sha256_payload(...)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .hashing import canonical_json, sha256_payload, sha256_text

__all__ = [
    "ExecutionAuthorizationError",
    "ExecutionAuthorizationValidationError",
    "ExecutionAuthorizationActorType",
    "ExecutionAuthorizationDecisionOutcome",
    "ExecutionAuthorizationScope",
    "ExecutionAuthorizationActor",
    "ExecutionAuthorizationPolicyRef",
    "ExecutionAuthorization",
    "ExecutionAuthorizationRequest",
    "ExecutionAuthorizationDecision",
    "ARTIFACT_VERSION",
    "SUPPORTED_ARTIFACT_VERSIONS",
    "AMENDED_ARTIFACT_VERSION",
    "build_execution_authorization",
    "build_execution_authorization_request",
    "build_execution_authorization_decision",
    "validate_execution_authorization_artifact",
    "validate_execution_authorization_request",
    "validate_execution_authorization_decision",
    "verify_execution_authorization_hash",
    "verify_execution_authorization_request_hash",
    "verify_execution_authorization_decision_hash",
    # EA-4B ExecutionAttempt domain
    "ExecutionAttemptError",
    "ExecutionAttemptNotFoundError",
    "ExecutionAttemptConflictError",
    "ExecutionAttemptClaimExpiredError",
    "ExecutionAttemptLimitError",
    "ExecutionAttemptIntegrityError",
    "ExecutionAttemptLineageError",
    "ExecutionAttemptStatus",
    "ExecutionAttemptActor",
    "ExecutionAttempt",
    "ATTEMPT_ARTIFACT_VERSION",
    "build_execution_attempt",
    "reconstruct_attempt",
]

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationError(ValueError):
    """Base error for the execution-authorization domain (EA-1).

    Domain/structural validation only. Persisted-tamper integrity exceptions
    (e.g. an ``ExecutionAuthorizationIntegrityError``) are intentionally NOT
    defined here; they belong to the future EA-2 store layer.
    """


class ExecutionAuthorizationValidationError(ExecutionAuthorizationError):
    """Raised when a domain artifact fails structural/semantic validation."""


# --------------------------------------------------------------------------- #
# EA-4B domain errors
# --------------------------------------------------------------------------- #


class ExecutionAttemptError(ExecutionAuthorizationError):
    """Base error for the execution-attempt domain (EA-4B).

    Domain/structural validation only. Persisted-tamper integrity exceptions
    (e.g. an ``ExecutionAttemptIntegrityError``) are intentionally NOT defined
    here; they belong to the future EA-4B store layer.
    """


class ExecutionAttemptNotFoundError(ExecutionAttemptError):
    """Raised when an expected ExecutionAttempt does not exist."""


class ExecutionAttemptConflictError(ExecutionAttemptError):
    """Raised when an attempt conflicts with an existing durable attempt."""


class ExecutionAttemptClaimExpiredError(ExecutionAttemptError):
    """Raised when the Claim has expired at attempt-creation time."""


class ExecutionAttemptLimitError(ExecutionAttemptError):
    """Raised when the attempt ceiling has been exhausted."""


class ExecutionAttemptIntegrityError(ExecutionAttemptError):
    """Raised on tampered or corrupt attempt data (future store layer use)."""


class ExecutionAttemptLineageError(ExecutionAttemptError):
    """Raised when attempt lineage does not match its Authorization/Claim."""


class ExecutionStateProjectionConflictError(ExecutionAttemptError):
    """Raised when a projection conflicts with an existing durable projection.

    EA-4D.4B: a second projection for the same start_result_id/target_state
    with differing material lineage is rejected, fail-closed. Never overwrites
    an already-committed immutable projection.
    """


# --------------------------------------------------------------------------- #
# EA-4D.4B ExecutionStateProjection domain (immutable EXECUTING projection)
# --------------------------------------------------------------------------- #


class ExecutionStateProjectionError(ExecutionAuthorizationError):
    """Base error for the execution-state projection domain (EA-4D.4B)."""


class ExecutionStateProjectionIntegrityError(ExecutionStateProjectionError):
    """Raised on tampered or corrupt projection data (store layer use)."""


class ExecutionStateProjectionIneligibleError(ExecutionStateProjectionError):
    """Raised when the persisted result is not eligible for projection.

    Covers FAILED outcome, missing result, malformed result hash, empty
    runtime_run_id, and authority-lineage mismatch. Never projects EXECUTING.
    """


# --------------------------------------------------------------------------- #
# Enums
#
# Repository enum precedent: tools/agent_post_writer.py uses
# ``class AgentPostStatus(str, Enum)``. We follow that exact style so enum
# members serialize as plain strings under canonical_json.
# --------------------------------------------------------------------------- #


class ExecutionAuthorizationActorType(str, Enum):
    HUMAN = "HUMAN"
    POLICY_SERVICE = "POLICY_SERVICE"
    SYSTEM = "SYSTEM"


class ExecutionAuthorizationDecisionOutcome(str, Enum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ARTIFACT_VERSION = "1"
# EA-3A amended Decision + Authorization artifacts (canonical structure changed
# incompatibly: Decision gained request_hash and dropped authorization_id from its
# hash preimage; Authorization gained request_id/request_hash/decision_id/
# decision_hash). Legacy Request artifacts remain at "1"; amended Decision/
# Authorization artifacts use "2".
SUPPORTED_ARTIFACT_VERSIONS = frozenset({"1", "2", "4"})
AMENDED_ARTIFACT_VERSION = "2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORIZATION_ID_RE = re.compile(r"^execution-authorization-[0-9a-f]{16}$")
_CLAIM_ID_RE = re.compile(r"^execution-authorization-claim-[0-9a-f]{16}$")
_ATTEMPT_ID_RE = re.compile(r"^execution-authorization-attempt-[0-9a-f]{16}$")

# Conservative frozen claim lifetime (EA-4A). Bounded, non-null.
DEFAULT_MAX_CLAIM_LIFETIME_SECONDS = 300
_REQUEST_ID_RE = re.compile(r"^execution-authorization-request-[0-9a-f]{16}$")
_DECISION_ID_RE = re.compile(r"^execution-authorization-decision-[0-9a-f]{16}$")

_ID_PREFIX = "execution-authorization-"
_REQUEST_ID_PREFIX = "execution-authorization-request-"
_DECISION_ID_PREFIX = "execution-authorization-decision-"
_CLAIM_ID_PREFIX = "execution-authorization-claim-"
_ATTEMPT_ID_PREFIX = "execution-authorization-attempt-"


# --------------------------------------------------------------------------- #
# Structured supporting domain types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionAuthorizationScope:
    """Least-authority scope bound into an authorization.

    ``attempt_limit >= 1`` is enforced at build time; consumption of attempts
    belongs to the future claim/store layer (EA-2/EA-4), not EA-1.
    """

    operation: str
    worker_class: Optional[str]
    input_hash: str
    attempt_limit: int
    max_runtime_seconds: Optional[int]


@dataclass(frozen=True)
class ExecutionAuthorizationActor:
    """Immutable actor identity metadata. No credentials or secrets."""

    actor_id: str
    actor_type: ExecutionAuthorizationActorType
    authority_role: str
    authentication_context: Optional[str]


@dataclass(frozen=True)
class ExecutionAuthorizationPolicyRef:
    """Immutable reference to the policy that governed a decision."""

    policy_id: str
    policy_version: str


# --------------------------------------------------------------------------- #
# Canonical dict helpers (plain dicts, enums -> .value)
# --------------------------------------------------------------------------- #


def _scope_to_dict(scope: ExecutionAuthorizationScope) -> dict[str, Any]:
    return {
        "operation": scope.operation,
        "worker_class": scope.worker_class,
        "input_hash": scope.input_hash,
        "attempt_limit": scope.attempt_limit,
        "max_runtime_seconds": scope.max_runtime_seconds,
    }


def _actor_to_dict(actor: ExecutionAuthorizationActor) -> dict[str, Any]:
    return {
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "authority_role": actor.authority_role,
        "authentication_context": actor.authentication_context,
    }


def _policy_to_dict(policy: ExecutionAuthorizationPolicyRef) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
    }


# --------------------------------------------------------------------------- #
# Validation helpers (pure, no external state)
# --------------------------------------------------------------------------- #


def _require_nonempty(name: str, value: Any) -> None:
    if not isinstance(value, str) or value == "":
        raise ExecutionAuthorizationValidationError(
            f"{name} must be a non-empty string"
        )


def _require_sha256(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        raise ExecutionAuthorizationValidationError(
            f"{name} must be a 64-character lowercase hex SHA-256 digest"
        )


def _require_utc_z_timestamp(name: str, value: Any) -> None:
    """Validate an absolute UTC RFC 3339 / ISO-8601 timestamp ending in Z.

    Fail-closed: naive/local timestamps without a ``Z`` suffix are rejected.
    Current-time lookup is never performed here.
    """
    if not isinstance(value, str):
        raise ExecutionAuthorizationValidationError(f"{name} must be a string timestamp")
    if not value.endswith("Z"):
        raise ExecutionAuthorizationValidationError(
            f"{name} must be an absolute UTC timestamp ending in 'Z' "
            f"(RFC 3339 / ISO-8601), got {value!r}"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionAuthorizationValidationError(
            f"{name} is not a valid ISO-8601 timestamp: {value!r}"
        ) from exc


def _validate_timestamp_order(issued_at: str, expires_at: Optional[str]) -> None:
    """Reject non-positive-duration or reversed expiry (fail-closed)."""
    if expires_at is None:
        return
    issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expires <= issued:
        raise ExecutionAuthorizationValidationError(
            "expires_at must be strictly after issued_at"
        )


def _validate_scope(scope: ExecutionAuthorizationScope) -> None:
    _require_nonempty("authorized_scope.operation", scope.operation)
    if scope.worker_class is not None:
        _require_nonempty("authorized_scope.worker_class", scope.worker_class)
    _require_sha256("authorized_scope.input_hash", scope.input_hash)
    if not isinstance(scope.attempt_limit, int) or isinstance(scope.attempt_limit, bool):
        raise ExecutionAuthorizationValidationError(
            "authorized_scope.attempt_limit must be an integer >= 1"
        )
    if scope.attempt_limit < 1:
        raise ExecutionAuthorizationValidationError(
            "authorized_scope.attempt_limit must be >= 1"
        )
    if scope.max_runtime_seconds is not None:
        if (
            not isinstance(scope.max_runtime_seconds, int)
            or isinstance(scope.max_runtime_seconds, bool)
            or scope.max_runtime_seconds < 1
        ):
            raise ExecutionAuthorizationValidationError(
                "authorized_scope.max_runtime_seconds must be a positive integer when present"
            )


def _validate_actor(actor: ExecutionAuthorizationActor) -> None:
    if not isinstance(actor, ExecutionAuthorizationActor):
        raise ExecutionAuthorizationValidationError("authorization_actor must be an ExecutionAuthorizationActor")
    _require_nonempty("authorization_actor.actor_id", actor.actor_id)
    if not isinstance(actor.actor_type, ExecutionAuthorizationActorType):
        raise ExecutionAuthorizationValidationError(
            "authorization_actor.actor_type must be a valid ExecutionAuthorizationActorType"
        )
    _require_nonempty("authorization_actor.authority_role", actor.authority_role)
    if actor.authentication_context is not None:
        _require_nonempty(
            "authorization_actor.authentication_context", actor.authentication_context
        )


def _validate_policy(policy: ExecutionAuthorizationPolicyRef) -> None:
    if not isinstance(policy, ExecutionAuthorizationPolicyRef):
        raise ExecutionAuthorizationValidationError("authorization_policy must be an ExecutionAuthorizationPolicyRef")
    _require_nonempty("authorization_policy.policy_id", policy.policy_id)
    _require_nonempty("authorization_policy.policy_version", policy.policy_version)


def _validate_artifact_version(artifact_version: str) -> None:
    _require_nonempty("artifact_version", artifact_version)
    if artifact_version not in SUPPORTED_ARTIFACT_VERSIONS:
        raise ExecutionAuthorizationValidationError(
            f"unsupported artifact_version {artifact_version!r}; "
            f"supported versions: {sorted(SUPPORTED_ARTIFACT_VERSIONS)}"
        )


def _validate_acceptance_binding(
    accepted_governance_artifact_id: str, accepted_governance_hash: str
) -> None:
    """A bare task identifier is never sufficient authorization evidence."""
    _require_nonempty(
        "accepted_governance_artifact_id", accepted_governance_artifact_id
    )
    _require_sha256("accepted_governance_hash", accepted_governance_hash)


# --------------------------------------------------------------------------- #
# Core artifact
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionAuthorization:
    authorization_id: str
    task_id: str
    accepted_governance_artifact_id: str
    accepted_governance_hash: str
    request_id: str
    request_hash: str
    decision_id: str
    decision_hash: str
    authorization_actor: ExecutionAuthorizationActor
    authorized_scope: ExecutionAuthorizationScope
    authorization_reason: str
    authorization_policy: ExecutionAuthorizationPolicyRef
    issued_at: str
    expires_at: Optional[str]
    nonce: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing.

        Excludes ``artifact_hash`` (set after hashing). Includes
        ``authorization_id`` so the recorded id participates in the hash, and
        the EA-3A binding fields (``request_id`` / ``request_hash`` /
        ``decision_id`` / ``decision_hash``) so the authorization is
        cryptographically bound to the exact Decision and Request that produced
        it.
        """
        return {
            "authorization_id": self.authorization_id,
            "task_id": self.task_id,
            "accepted_governance_artifact_id": self.accepted_governance_artifact_id,
            "accepted_governance_hash": self.accepted_governance_hash,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "decision_id": self.decision_id,
            "decision_hash": self.decision_hash,
            "authorization_actor": _actor_to_dict(self.authorization_actor),
            "authorized_scope": _scope_to_dict(self.authorized_scope),
            "authorization_reason": self.authorization_reason,
            "authorization_policy": _policy_to_dict(self.authorization_policy),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "artifact_version": self.artifact_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        """Pure domain verification: stored hash vs recomputed canonical hash."""
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


@dataclass(frozen=True)
class ExecutionClaimant:
    """Structured claimant identity. Does NOT itself authorize execution.

    Examples: worker-manager, scheduler, runtime-orchestrator,
    operator-mediated-runtime. A claimant is the actor that reserved/consumed
    the Authorization for a future execution attempt; it is recorded explicitly
    and never silently substituted.
    """

    claimant_id: str
    claimant_type: str
    claimant_context: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claimant_id": self.claimant_id,
            "claimant_type": self.claimant_type,
            "claimant_context": self.claimant_context,
        }


def _claimant_from_dict(d: Mapping[str, Any]) -> ExecutionClaimant:
    return ExecutionClaimant(
        claimant_id=d["claimant_id"],
        claimant_type=d["claimant_type"],
        claimant_context=d.get("claimant_context"),
    )


@dataclass(frozen=True)
class ExecutionClaim:
    """A durable, immutable reservation of an ExecutionAuthorization for a
    future execution attempt. Created by EA-4A only.

    CLAIMED != EXECUTING: a persisted Claim means a specific claimant reserved
    the Authorization; it does NOT mean a process, worker, or command started.
    The Claim cryptographically binds to the exact Authorization, Request,
    Decision, and task via the linkage fields below.

    One active Claim per Authorization is enforced at persistence (UNIQUE
    authorization_id). No worker/execution state is created.
    """

    claim_id: str
    authorization_id: str
    authorization_hash: str
    request_id: str
    request_hash: str
    decision_id: str
    decision_hash: str
    task_id: str
    claimant: ExecutionClaimant
    claimed_at: str  # absolute UTC RFC3339/ISO ending Z
    claim_expires_at: str  # absolute UTC RFC3339/ISO ending Z; > claimed_at
    authorization_policy: ExecutionAuthorizationPolicyRef
    claim_reason: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing.

        Excludes ``artifact_hash`` (set after hashing). Includes the full
        cryptographic lineage (authorization_id/hash, request_id/hash,
        decision_id/hash, task_id) and the claim's own time semantics so the
        Claim is bound to the exact Authorization and cannot be repurposed.
        """
        return {
            "claim_id": self.claim_id,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "decision_id": self.decision_id,
            "decision_hash": self.decision_hash,
            "task_id": self.task_id,
            "claimant": self.claimant.to_dict(),
            "claimed_at": self.claimed_at,
            "claim_expires_at": self.claim_expires_at,
            "authorization_policy": _policy_to_dict(self.authorization_policy),
            "claim_reason": self.claim_reason,
            "artifact_version": self.artifact_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        """Pure domain verification: stored hash vs recomputed canonical hash."""
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


@dataclass(frozen=True)
class ExecutionAuthorizationRequest:
    """A request for execution authority. Carries ZERO execution authority."""

    request_id: str
    task_id: str
    accepted_governance_artifact_id: str
    accepted_governance_hash: str
    requested_scope: ExecutionAuthorizationScope
    requesting_actor: ExecutionAuthorizationActor
    authorization_policy: ExecutionAuthorizationPolicyRef
    requested_at: str
    request_reason: str
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "accepted_governance_artifact_id": self.accepted_governance_artifact_id,
            "accepted_governance_hash": self.accepted_governance_hash,
            "requested_scope": _scope_to_dict(self.requested_scope),
            "requesting_actor": _actor_to_dict(self.requesting_actor),
            "authorization_policy": _policy_to_dict(self.authorization_policy),
            "requested_at": self.requested_at,
            "request_reason": self.request_reason,
            "artifact_version": self.artifact_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


@dataclass(frozen=True)
class ExecutionAuthorizationDecision:
    """An immutable GRANTED/DENIED decision. Does not issue the authorization."""

    decision_id: str
    request_id: str
    request_hash: str
    task_id: str
    decision_actor: ExecutionAuthorizationActor
    outcome: ExecutionAuthorizationDecisionOutcome
    decision_reason: str
    authorization_id: Optional[str]
    authorization_policy: ExecutionAuthorizationPolicyRef
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        # NOTE: authorization_id is intentionally EXCLUDED from the canonical
        # preimage (EA-3A, acyclic Model A). It remains a non-hash-bound forward
        # linkage from Decision -> Authorization so that decision_id/decision_hash
        # depend only on the request + decision content, never on the
        # authorization identity. This keeps the identity graph a DAG:
        # Request -> Decision -> Authorization.
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "task_id": self.task_id,
            "decision_actor": _actor_to_dict(self.decision_actor),
            "outcome": self.outcome.value,
            "decision_reason": self.decision_reason,
            "authorization_policy": _policy_to_dict(self.authorization_policy),
            "artifact_version": self.artifact_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# EA-4B ExecutionAttempt domain
# --------------------------------------------------------------------------- #


class ExecutionAttemptStatus(str, Enum):
    """Pre-execution attempt state only.

    EA-4B deliberately stops before ``EXECUTING``. ``RECORDED`` means a
    durable ExecutionAttempt has been persisted; it does NOT mean a worker
    has been launched or that execution has begun.
    """

    RECORDED = "RECORDED"


# ExecutionAttempt artifact version (EA-4B).
ATTEMPT_ARTIFACT_VERSION = "1"


@dataclass(frozen=True)
class ExecutionAttemptActor:
    """Structured identity of the component requesting claim consumption.

    This identity represents the system component requesting consumption of
    the Claim into an Attempt. It does NOT grant worker execution authority.
    """

    actor_id: str
    actor_type: str
    actor_context: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "actor_context": self.actor_context,
        }


@dataclass(frozen=True)
class ExecutionAttempt:
    """A durable, immutable record that a valid ExecutionClaim has been
    consumed for a future execution attempt. Created by EA-4B only.

    EXECUTION_ATTEMPT_RECORDED != EXECUTING: a persisted Attempt means a
    specific claimant reserved and consumed the Claim; it does NOT mean a
    process, worker, or command started. The Attempt cryptographically binds
    to the exact Authorization, Request, Decision, Claim, and task via the
    linkage fields below.

    One durable Attempt per attempt_number per Authorization is enforced at
    persistence. No worker/execution state is created.
    """

    attempt_id: str
    authorization_id: str
    authorization_hash: str
    request_id: str
    request_hash: str
    decision_id: str
    decision_hash: str
    claim_id: str
    claim_hash: str
    task_id: str
    attempt_number: int
    attempt_actor_id: str
    attempt_actor_type: str
    attempt_actor_context: Optional[str]
    attempt_requested_at: str  # absolute UTC RFC3339/ISO ending Z
    attempt_recorded_at: str  # absolute UTC RFC3339/ISO ending Z
    claim_expires_at: str  # absolute UTC RFC3339/ISO ending Z
    must_start_by: str  # absolute UTC RFC3339/ISO ending Z
    input_hash: str
    operation: str
    worker_class: Optional[str]
    status: ExecutionAttemptStatus
    artifact_version: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing.

        Excludes ``artifact_hash`` (set after hashing). Includes the full
        cryptographic lineage (authorization_id/hash, request_id/hash,
        decision_id/hash, claim_id/hash, task_id) and the attempt's own time
        semantics so the Attempt is bound to the exact Claim and cannot be
        repurposed.
        """
        return {
            "attempt_id": self.attempt_id,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "decision_id": self.decision_id,
            "decision_hash": self.decision_hash,
            "claim_id": self.claim_id,
            "claim_hash": self.claim_hash,
            "task_id": self.task_id,
            "attempt_number": self.attempt_number,
            "attempt_actor_id": self.attempt_actor_id,
            "attempt_actor_type": self.attempt_actor_type,
            "attempt_actor_context": self.attempt_actor_context,
            "attempt_requested_at": self.attempt_requested_at,
            "attempt_recorded_at": self.attempt_recorded_at,
            "claim_expires_at": self.claim_expires_at,
            "must_start_by": self.must_start_by,
            "input_hash": self.input_hash,
            "operation": self.operation,
            "worker_class": self.worker_class,
            "status": self.status.value,
            "artifact_version": self.artifact_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        """Pure domain verification: stored hash vs recomputed canonical hash."""
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash
#
# The builder validates inputs, derives the deterministic artifact id from a
# canonical preimage that excludes the id, then derives artifact_hash from the
# full canonical dict (excluding the hash). This mirrors AcceptanceArtifact.
# --------------------------------------------------------------------------- #


def _derive_id(prefix: str, preimage: dict[str, Any]) -> str:
    return prefix + sha256_payload(preimage)[:16]


def build_execution_authorization(
    *,
    task_id: str,
    accepted_governance_artifact_id: str,
    accepted_governance_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
    authorization_actor: ExecutionAuthorizationActor,
    authorized_scope: ExecutionAuthorizationScope,
    authorization_reason: str,
    authorization_policy: ExecutionAuthorizationPolicyRef,
    issued_at: str,
    expires_at: Optional[str],
    nonce: str,
    artifact_version: str = AMENDED_ARTIFACT_VERSION,
) -> ExecutionAuthorization:
    _require_nonempty("task_id", task_id)
    _validate_acceptance_binding(accepted_governance_artifact_id, accepted_governance_hash)
    _require_nonempty("request_id", request_id)
    _require_sha256("request_hash", request_hash)
    _require_nonempty("decision_id", decision_id)
    _require_sha256("decision_hash", decision_hash)
    _validate_actor(authorization_actor)
    _validate_scope(authorized_scope)
    _require_nonempty("authorization_reason", authorization_reason)
    _validate_policy(authorization_policy)
    _require_utc_z_timestamp("issued_at", issued_at)
    if expires_at is not None:
        _require_utc_z_timestamp("expires_at", expires_at)
    _validate_timestamp_order(issued_at, expires_at)
    _require_nonempty("nonce", nonce)
    _validate_artifact_version(artifact_version)

    preimage = {
        "task_id": task_id,
        "accepted_governance_artifact_id": accepted_governance_artifact_id,
        "accepted_governance_hash": accepted_governance_hash,
        "request_id": request_id,
        "request_hash": request_hash,
        "decision_id": decision_id,
        "decision_hash": decision_hash,
        "authorization_actor": _actor_to_dict(authorization_actor),
        "authorized_scope": _scope_to_dict(authorized_scope),
        "authorization_reason": authorization_reason,
        "authorization_policy": _policy_to_dict(authorization_policy),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
        "artifact_version": artifact_version,
    }
    authorization_id = _derive_id(_ID_PREFIX, preimage)
    full = {**preimage, "authorization_id": authorization_id}
    if not _AUTHORIZATION_ID_RE.match(authorization_id):
        raise ExecutionAuthorizationValidationError(
            f"derived authorization_id is malformed: {authorization_id!r}"
        )
    artifact_hash = sha256_payload(full)
    return ExecutionAuthorization(
        authorization_id=authorization_id,
        task_id=task_id,
        accepted_governance_artifact_id=accepted_governance_artifact_id,
        accepted_governance_hash=accepted_governance_hash,
        request_id=request_id,
        request_hash=request_hash,
        decision_id=decision_id,
        decision_hash=decision_hash,
        authorization_actor=authorization_actor,
        authorized_scope=authorized_scope,
        authorization_reason=authorization_reason,
        authorization_policy=authorization_policy,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


def build_execution_authorization_request(
    *,
    task_id: str,
    accepted_governance_artifact_id: str,
    accepted_governance_hash: str,
    requested_scope: ExecutionAuthorizationScope,
    requesting_actor: ExecutionAuthorizationActor,
    authorization_policy: ExecutionAuthorizationPolicyRef,
    requested_at: str,
    request_reason: str,
    artifact_version: str = ARTIFACT_VERSION,
) -> ExecutionAuthorizationRequest:
    _require_nonempty("task_id", task_id)
    _validate_acceptance_binding(accepted_governance_artifact_id, accepted_governance_hash)
    _validate_actor(requesting_actor)
    _validate_scope(requested_scope)
    _validate_policy(authorization_policy)
    _require_utc_z_timestamp("requested_at", requested_at)
    _require_nonempty("request_reason", request_reason)
    _validate_artifact_version(artifact_version)

    preimage = {
        "task_id": task_id,
        "accepted_governance_artifact_id": accepted_governance_artifact_id,
        "accepted_governance_hash": accepted_governance_hash,
        "requested_scope": _scope_to_dict(requested_scope),
        "requesting_actor": _actor_to_dict(requesting_actor),
        "authorization_policy": _policy_to_dict(authorization_policy),
        "requested_at": requested_at,
        "request_reason": request_reason,
        "artifact_version": artifact_version,
    }
    request_id = _derive_id(_REQUEST_ID_PREFIX, preimage)
    full = {**preimage, "request_id": request_id}
    if not _REQUEST_ID_RE.match(request_id):
        raise ExecutionAuthorizationValidationError(
            f"derived request_id is malformed: {request_id!r}"
        )
    artifact_hash = sha256_payload(full)
    return ExecutionAuthorizationRequest(
        request_id=request_id,
        task_id=task_id,
        accepted_governance_artifact_id=accepted_governance_artifact_id,
        accepted_governance_hash=accepted_governance_hash,
        requested_scope=requested_scope,
        requesting_actor=requesting_actor,
        authorization_policy=authorization_policy,
        requested_at=requested_at,
        request_reason=request_reason,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


def build_execution_authorization_decision(
    *,
    request_id: str,
    request_hash: str,
    task_id: str,
    decision_actor: ExecutionAuthorizationActor,
    outcome: ExecutionAuthorizationDecisionOutcome,
    decision_reason: str,
    authorization_id: Optional[str],
    authorization_policy: ExecutionAuthorizationPolicyRef,
    artifact_version: str = AMENDED_ARTIFACT_VERSION,
) -> ExecutionAuthorizationDecision:
    _require_nonempty("request_id", request_id)
    _require_sha256("request_hash", request_hash)
    _require_nonempty("task_id", task_id)
    _validate_actor(decision_actor)
    if not isinstance(outcome, ExecutionAuthorizationDecisionOutcome):
        raise ExecutionAuthorizationValidationError(
            "outcome must be a valid ExecutionAuthorizationDecisionOutcome"
        )
    _require_nonempty("decision_reason", decision_reason)
    _validate_policy(authorization_policy)
    _validate_artifact_version(artifact_version)

    # Cross-field invariant (GRANTED requires id; DENIED forbids id).
    if outcome is ExecutionAuthorizationDecisionOutcome.GRANTED:
        _require_nonempty("authorization_id", authorization_id or "")
    elif outcome is ExecutionAuthorizationDecisionOutcome.DENIED:
        if authorization_id is not None:
            raise ExecutionAuthorizationValidationError(
                "a DENIED decision must not carry an authorization_id"
            )

    # NOTE (EA-3A acyclic Model A): authorization_id is deliberately excluded
    # from the hash preimage. It is non-hash-bound forward linkage only; the
    # decision identity depends on request + decision content alone.
    preimage = {
        "request_id": request_id,
        "request_hash": request_hash,
        "task_id": task_id,
        "decision_actor": _actor_to_dict(decision_actor),
        "outcome": outcome.value,
        "decision_reason": decision_reason,
        "authorization_policy": _policy_to_dict(authorization_policy),
        "artifact_version": artifact_version,
    }
    decision_id = _derive_id(_DECISION_ID_PREFIX, preimage)
    full = {**preimage, "decision_id": decision_id}
    if not _DECISION_ID_RE.match(decision_id):
        raise ExecutionAuthorizationValidationError(
            f"derived decision_id is malformed: {decision_id!r}"
        )
    artifact_hash = sha256_payload(full)
    return ExecutionAuthorizationDecision(
        decision_id=decision_id,
        request_id=request_id,
        request_hash=request_hash,
        task_id=task_id,
        decision_actor=decision_actor,
        outcome=outcome,
        decision_reason=decision_reason,
        authorization_id=authorization_id,
        authorization_policy=authorization_policy,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


# --------------------------------------------------------------------------- #
# Validation / verification entry points
# --------------------------------------------------------------------------- #


def validate_execution_authorization_artifact(artifact: ExecutionAuthorization) -> None:
    if not isinstance(artifact, ExecutionAuthorization):
        raise ExecutionAuthorizationValidationError("expected ExecutionAuthorization")
    if not _AUTHORIZATION_ID_RE.match(artifact.authorization_id):
        raise ExecutionAuthorizationValidationError("authorization_id format invalid")
    _require_nonempty("request_id", artifact.request_id)
    _require_sha256("request_hash", artifact.request_hash)
    _require_nonempty("decision_id", artifact.decision_id)
    _require_sha256("decision_hash", artifact.decision_hash)
    _validate_acceptance_binding(
        artifact.accepted_governance_artifact_id, artifact.accepted_governance_hash
    )
    _validate_actor(artifact.authorization_actor)
    _validate_scope(artifact.authorized_scope)
    _require_utc_z_timestamp("issued_at", artifact.issued_at)
    if artifact.expires_at is not None:
        _require_utc_z_timestamp("expires_at", artifact.expires_at)
    _validate_timestamp_order(artifact.issued_at, artifact.expires_at)
    _validate_artifact_version(artifact.artifact_version)
    if not artifact.verify_hash():
        raise ExecutionAuthorizationValidationError(
            "artifact_hash does not match the canonical payload (tampered or malformed)"
        )


def validate_execution_authorization_request(artifact: ExecutionAuthorizationRequest) -> None:
    if not isinstance(artifact, ExecutionAuthorizationRequest):
        raise ExecutionAuthorizationValidationError("expected ExecutionAuthorizationRequest")
    if not _REQUEST_ID_RE.match(artifact.request_id):
        raise ExecutionAuthorizationValidationError("request_id format invalid")
    _validate_acceptance_binding(
        artifact.accepted_governance_artifact_id, artifact.accepted_governance_hash
    )
    _validate_actor(artifact.requesting_actor)
    _validate_scope(artifact.requested_scope)
    _require_utc_z_timestamp("requested_at", artifact.requested_at)
    _validate_artifact_version(artifact.artifact_version)
    if not artifact.verify_hash():
        raise ExecutionAuthorizationValidationError(
            "artifact_hash does not match the canonical payload (tampered or malformed)"
        )


def validate_execution_authorization_decision(artifact: ExecutionAuthorizationDecision) -> None:
    if not isinstance(artifact, ExecutionAuthorizationDecision):
        raise ExecutionAuthorizationValidationError("expected ExecutionAuthorizationDecision")
    if not _DECISION_ID_RE.match(artifact.decision_id):
        raise ExecutionAuthorizationValidationError("decision_id format invalid")
    _require_sha256("request_hash", artifact.request_hash)
    _validate_actor(artifact.decision_actor)
    _validate_artifact_version(artifact.artifact_version)
    if artifact.outcome is ExecutionAuthorizationDecisionOutcome.GRANTED:
        _require_nonempty("authorization_id", artifact.authorization_id or "")
    elif artifact.outcome is ExecutionAuthorizationDecisionOutcome.DENIED:
        if artifact.authorization_id is not None:
            raise ExecutionAuthorizationValidationError(
                "a DENIED decision must not carry an authorization_id"
            )
    if not artifact.verify_hash():
        raise ExecutionAuthorizationValidationError(
            "artifact_hash does not match the canonical payload (tampered or malformed)"
        )


def verify_execution_authorization_hash(artifact: ExecutionAuthorization) -> bool:
    return artifact.verify_hash()


def verify_execution_authorization_request_hash(artifact: ExecutionAuthorizationRequest) -> bool:
    return artifact.verify_hash()


def verify_execution_authorization_decision_hash(artifact: ExecutionAuthorizationDecision) -> bool:
    return artifact.verify_hash()


def _actor_from_dict(d: Mapping[str, Any]) -> ExecutionAuthorizationActor:
    actor_type = d.get("actor_type")
    if isinstance(actor_type, str):
        actor_type = ExecutionAuthorizationActorType(actor_type)
    return ExecutionAuthorizationActor(
        actor_id=d["actor_id"],
        actor_type=actor_type,
        authority_role=d["authority_role"],
        authentication_context=d.get("authentication_context"),
    )


def _scope_from_dict(d: Mapping[str, Any]) -> ExecutionAuthorizationScope:
    return ExecutionAuthorizationScope(
        operation=d["operation"],
        worker_class=d.get("worker_class"),
        input_hash=d.get("input_hash"),
        attempt_limit=d.get("attempt_limit"),
        max_runtime_seconds=d.get("max_runtime_seconds"),
    )


def _policy_from_dict(d: Mapping[str, Any]) -> ExecutionAuthorizationPolicyRef:
    return ExecutionAuthorizationPolicyRef(
        policy_id=d["policy_id"],
        policy_version=d["policy_version"],
    )


def reconstruct_authorization(payload: Mapping[str, Any]) -> ExecutionAuthorization:
    """Rebuild an immutable ExecutionAuthorization from its canonical dict (EA-2 reload).

    The canonical dict stores enums as their string values and nested dataclasses
    as plain dicts; this restores the domain objects without re-deriving the
    artifact id/hash (those are taken verbatim, and verify_hash re-checks them).
    """
    d = dict(payload)
    d.pop("artifact_hash", None)
    d.pop("authorization_id", None)
    d["authorization_actor"] = _actor_from_dict(d["authorization_actor"])
    d["authorized_scope"] = _scope_from_dict(d["authorized_scope"])
    d["authorization_policy"] = _policy_from_dict(d["authorization_policy"])
    return build_execution_authorization(**d)


def reconstruct_request(payload: Mapping[str, Any]) -> ExecutionAuthorizationRequest:
    d = dict(payload)
    d.pop("artifact_hash", None)
    d.pop("request_id", None)
    d["requested_scope"] = _scope_from_dict(d["requested_scope"])
    d["requesting_actor"] = _actor_from_dict(d["requesting_actor"])
    d["authorization_policy"] = _policy_from_dict(d["authorization_policy"])
    return build_execution_authorization_request(**d)


def reconstruct_decision(payload: Mapping[str, Any]) -> ExecutionAuthorizationDecision:
    d = dict(payload)
    d.pop("artifact_hash", None)
    d.pop("decision_id", None)
    # authorization_id is a non-hash-bound forward linkage (EA-3A acyclic Model
    # A): it is excluded from the canonical payload/hash preimage, so it may be
    # absent from a pure canonical dict. Default to None when not supplied.
    d["authorization_id"] = d.get("authorization_id")
    d["decision_actor"] = _actor_from_dict(d["decision_actor"])
    d["authorization_policy"] = _policy_from_dict(d["authorization_policy"])
    outcome = d.get("outcome")
    if isinstance(outcome, str):
        d["outcome"] = ExecutionAuthorizationDecisionOutcome(outcome)
    return build_execution_authorization_decision(**d)


def build_execution_claim(
    *,
    authorization_id: str,
    authorization_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
    task_id: str,
    claimant: ExecutionClaimant,
    claimed_at: str,  # absolute UTC RFC3339/ISO ending Z
    claim_expires_at: str,  # absolute UTC RFC3339/ISO ending Z; > claimed_at
    authorization_policy: ExecutionAuthorizationPolicyRef,
    claim_reason: str,
    artifact_version: str = AMENDED_ARTIFACT_VERSION,
) -> ExecutionClaim:
    """Build a durable, immutable ExecutionClaim bound to its Authorization.

    The Claim cryptographically binds to the exact Authorization (id + hash),
    Request (id + hash), Decision (id + hash), and task. ``claim_expires_at``
    must be absolute UTC ending in ``Z`` and strictly after ``claimed_at``.

    ``claimed_at``/``claim_expires_at`` are supplied by the caller (typically
    the claim service via an injected clock seam); this builder only validates
    and derives the deterministic ``claim_id`` from the canonical preimage.
    """
    _require_nonempty("authorization_id", authorization_id)
    _require_sha256("authorization_hash", authorization_hash)
    _require_nonempty("request_id", request_id)
    _require_sha256("request_hash", request_hash)
    _require_nonempty("decision_id", decision_id)
    _require_sha256("decision_hash", decision_hash)
    _require_nonempty("task_id", task_id)
    if not isinstance(claimant, ExecutionClaimant):
        raise ExecutionAuthorizationValidationError(
            "claimant must be an ExecutionClaimant"
        )
    _require_utc_z_timestamp("claimed_at", claimed_at)
    _require_utc_z_timestamp("claim_expires_at", claim_expires_at)
    _validate_timestamp_order(claimed_at, claim_expires_at)
    _validate_policy(authorization_policy)
    if not claim_reason:
        raise ExecutionAuthorizationValidationError("claim_reason must be non-empty")
    _validate_artifact_version(artifact_version)

    preimage = {
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "request_id": request_id,
        "request_hash": request_hash,
        "decision_id": decision_id,
        "decision_hash": decision_hash,
        "task_id": task_id,
        "claimant": claimant.to_dict(),
        "claimed_at": claimed_at,
        "claim_expires_at": claim_expires_at,
        "authorization_policy": _policy_to_dict(authorization_policy),
        "claim_reason": claim_reason,
        "artifact_version": artifact_version,
    }
    claim_id = _derive_id(_CLAIM_ID_PREFIX, preimage)
    full = {**preimage, "claim_id": claim_id}
    if not _CLAIM_ID_RE.match(claim_id):
        raise ExecutionAuthorizationValidationError(
            f"derived claim_id is malformed: {claim_id!r}"
        )
    artifact_hash = sha256_payload(full)
    return ExecutionClaim(
        claim_id=claim_id,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        request_id=request_id,
        request_hash=request_hash,
        decision_id=decision_id,
        decision_hash=decision_hash,
        task_id=task_id,
        claimant=claimant,
        claimed_at=claimed_at,
        claim_expires_at=claim_expires_at,
        authorization_policy=authorization_policy,
        claim_reason=claim_reason,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


def reconstruct_claim(payload: Mapping[str, Any]) -> ExecutionClaim:
    """Rebuild an immutable ExecutionClaim from its canonical dict (EA-2 reload)."""
    d = dict(payload)
    d.pop("artifact_hash", None)
    d.pop("claim_id", None)
    d["claimant"] = _claimant_from_dict(d["claimant"])
    d["authorization_policy"] = _policy_from_dict(d["authorization_policy"])
    return build_execution_claim(**d)


# --------------------------------------------------------------------------- #
# EA-4B ExecutionAttempt: validation helpers
# --------------------------------------------------------------------------- #


def _validate_attempt_actor(actor: ExecutionAttemptActor) -> None:
    if not isinstance(actor, ExecutionAttemptActor):
        raise ExecutionAttemptError("attempt_actor must be an ExecutionAttemptActor")
    _require_nonempty("attempt_actor.actor_id", actor.actor_id)
    _require_nonempty("attempt_actor.actor_type", actor.actor_type)
    if actor.actor_context is not None:
        _require_nonempty("attempt_actor.actor_context", actor.actor_context)


def _validate_attempt_status(status: ExecutionAttemptStatus) -> None:
    if not isinstance(status, ExecutionAttemptStatus):
        raise ExecutionAttemptError("status must be a valid ExecutionAttemptStatus")


# --------------------------------------------------------------------------- #
# EA-4B ExecutionAttempt: builder
# --------------------------------------------------------------------------- #


def build_execution_attempt(
    *,
    authorization_id: str,
    authorization_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
    claim_id: str,
    claim_hash: str,
    task_id: str,
    attempt_number: int,
    attempt_actor: ExecutionAttemptActor,
    attempt_requested_at: str,
    attempt_recorded_at: str,
    claim_expires_at: str,
    must_start_by: str,
    input_hash: str,
    operation: str,
    worker_class: Optional[str],
    status: ExecutionAttemptStatus = ExecutionAttemptStatus.RECORDED,
    artifact_version: str = ATTEMPT_ARTIFACT_VERSION,
) -> ExecutionAttempt:
    """Build a durable, immutable ExecutionAttempt bound to its Claim.

    The Attempt cryptographically binds to the exact Authorization (id + hash),
    Request (id + hash), Decision (id + hash), Claim (id + hash), and task.
    ``must_start_by`` must be absolute UTC ending in ``Z`` and is bounded by
    the Claim lifetime (callers enforce that; this builder validates structure
    only).

    ``attempt_number`` must be >= 1.
    """
    _require_nonempty("authorization_id", authorization_id)
    _require_sha256("authorization_hash", authorization_hash)
    _require_nonempty("request_id", request_id)
    _require_sha256("request_hash", request_hash)
    _require_nonempty("decision_id", decision_id)
    _require_sha256("decision_hash", decision_hash)
    _require_nonempty("claim_id", claim_id)
    _require_sha256("claim_hash", claim_hash)
    _require_nonempty("task_id", task_id)
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool):
        raise ExecutionAttemptError("attempt_number must be an integer >= 1")
    if attempt_number < 1:
        raise ExecutionAttemptError("attempt_number must be >= 1")
    _validate_attempt_actor(attempt_actor)
    _require_utc_z_timestamp("attempt_requested_at", attempt_requested_at)
    _require_utc_z_timestamp("attempt_recorded_at", attempt_recorded_at)
    _require_utc_z_timestamp("claim_expires_at", claim_expires_at)
    _require_utc_z_timestamp("must_start_by", must_start_by)
    _require_sha256("input_hash", input_hash)
    _require_nonempty("operation", operation)
    if worker_class is not None:
        _require_nonempty("worker_class", worker_class)
    _validate_attempt_status(status)

    preimage = {
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "request_id": request_id,
        "request_hash": request_hash,
        "decision_id": decision_id,
        "decision_hash": decision_hash,
        "claim_id": claim_id,
        "claim_hash": claim_hash,
        "task_id": task_id,
        "attempt_number": attempt_number,
        "attempt_actor_id": attempt_actor.actor_id,
        "attempt_actor_type": attempt_actor.actor_type,
        "attempt_actor_context": attempt_actor.actor_context,
        "attempt_requested_at": attempt_requested_at,
        "attempt_recorded_at": attempt_recorded_at,
        "claim_expires_at": claim_expires_at,
        "must_start_by": must_start_by,
        "input_hash": input_hash,
        "operation": operation,
        "worker_class": worker_class,
        "status": status.value,
        "artifact_version": artifact_version,
    }
    attempt_id = _derive_id(_ATTEMPT_ID_PREFIX, preimage)
    full = {**preimage, "attempt_id": attempt_id}
    if not _ATTEMPT_ID_RE.match(attempt_id):
        raise ExecutionAttemptError(
            f"derived attempt_id is malformed: {attempt_id!r}"
        )
    artifact_hash = sha256_payload(full)
    return ExecutionAttempt(
        attempt_id=attempt_id,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        request_id=request_id,
        request_hash=request_hash,
        decision_id=decision_id,
        decision_hash=decision_hash,
        claim_id=claim_id,
        claim_hash=claim_hash,
        task_id=task_id,
        attempt_number=attempt_number,
        attempt_actor_id=attempt_actor.actor_id,
        attempt_actor_type=attempt_actor.actor_type,
        attempt_actor_context=attempt_actor.actor_context,
        attempt_requested_at=attempt_requested_at,
        attempt_recorded_at=attempt_recorded_at,
        claim_expires_at=claim_expires_at,
        must_start_by=must_start_by,
        input_hash=input_hash,
        operation=operation,
        worker_class=worker_class,
        status=status,
        artifact_version=artifact_version,
        artifact_hash=artifact_hash,
    )


# --------------------------------------------------------------------------- #
# EA-4B ExecutionAttempt: reconstruction
# --------------------------------------------------------------------------- #


def _attempt_actor_from_dict(d: Mapping[str, Any]) -> ExecutionAttemptActor:
    return ExecutionAttemptActor(
        actor_id=d["actor_id"],
        actor_type=d["actor_type"],
        actor_context=d.get("actor_context"),
    )


def reconstruct_attempt(payload: Mapping[str, Any]) -> ExecutionAttempt:
    """Rebuild an immutable ExecutionAttempt from its canonical dict."""
    d = dict(payload)
    d.pop("artifact_hash", None)
    d.pop("attempt_id", None)
    # Remove the flat actor fields and build the structured actor for the builder
    actor = ExecutionAttemptActor(
        actor_id=d.pop("attempt_actor_id"),
        actor_type=d.pop("attempt_actor_type"),
        actor_context=d.pop("attempt_actor_context", None),
    )
    d["attempt_actor"] = actor
    status = d.get("status")
    if isinstance(status, str):
        d["status"] = ExecutionAttemptStatus(status)
    return build_execution_attempt(**d)



# --------------------------------------------------------------------------- #
# EA-4D.4B ExecutionStateProjection: immutable EXECUTING projection
# --------------------------------------------------------------------------- #


PROJECTION_ARTIFACT_VERSION = "1"

_PROJECTION_ID_PREFIX = "esproj"
_PROJECTION_ID_RE = re.compile(r"^esproj_[0-9a-f]{64}$")


def _derive_projection_id(preimage: dict) -> str:
    return "esproj_" + sha256_payload(preimage)[-64:]


def build_execution_state_projection(
    *,
    start_result_id: str,
    start_result_hash: str,
    launch_attempt_id: str,
    launch_attempt_hash: str,
    route_id: str,
    route_hash: str,
    authorization_id: str,
    authorization_hash: str,
    attempt_id: str,
    attempt_hash: str,
    task_id: str,
    worker_id: str,
    worker_version: str,
    runtime_run_id: str,
    target_state: str = "EXECUTING",
    projected_at: Optional[str] = None,
) -> "ExecutionStateProjection":
    """Build an immutable EXECUTING projection bound to a STARTED result.

    The projection_id is deterministic and timing-independent; projected_at is
    provenance metadata only and is excluded from identity/integrity. The
    artifact_hash binds all material lineage (projected_at excluded), using the
    repository canonical_json + sha256_payload convention.
    """
    if target_state != "EXECUTING":
        raise ExecutionStateProjectionError(
            f"only EXECUTING projection is supported; got {target_state!r}")
    if not start_result_id or not start_result_hash:
        raise ExecutionStateProjectionError(
            "start_result_id and start_result_hash are required")
    if not runtime_run_id:
        raise ExecutionStateProjectionError(
            "runtime_run_id is required for an EXECUTING projection")

    projection_id = _derive_projection_id({
        "schema": "ea4d4b-executing-projection-id-v1",
        "start_result_id": start_result_id,
        "target_state": target_state,
    })
    canonical = {
        "schema": "ea4d4b-executing-projection-v1",
        "projection_id": projection_id,
        "start_result_id": start_result_id,
        "start_result_hash": start_result_hash,
        "launch_attempt_id": launch_attempt_id,
        "launch_attempt_hash": launch_attempt_hash,
        "route_id": route_id,
        "route_hash": route_hash,
        "authorization_id": authorization_id,
        "authorization_hash": authorization_hash,
        "attempt_id": attempt_id,
        "attempt_hash": attempt_hash,
        "task_id": task_id,
        "worker_id": worker_id,
        "worker_version": worker_version,
        "runtime_run_id": runtime_run_id,
        "target_state": target_state,
    }
    artifact_hash = sha256_payload(canonical)
    canonical_payload = canonical_json(canonical)
    payload_sha256 = sha256_text(canonical_payload)
    return ExecutionStateProjection(
        projection_id=projection_id,
        artifact_hash=artifact_hash,
        start_result_id=start_result_id,
        start_result_hash=start_result_hash,
        launch_attempt_id=launch_attempt_id,
        launch_attempt_hash=launch_attempt_hash,
        route_id=route_id,
        route_hash=route_hash,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        task_id=task_id,
        worker_id=worker_id,
        worker_version=worker_version,
        runtime_run_id=runtime_run_id,
        target_state=target_state,
        projected_at=projected_at or _now_iso_z(),
        artifact_version=PROJECTION_ARTIFACT_VERSION,
        canonical_payload=canonical_payload,
        payload_sha256=payload_sha256,
    )


def _now_iso_z() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ExecutionStateProjection:
    """Immutable authority-side EXECUTING projection (EA-4D.4B).

    EXECUTING is *derived* from the committed presence of this immutable
    artifact; the ExecutionAttempt.status remains RECORDED forever. The
    projection never mutates historical authority artifacts.
    """

    projection_id: str
    artifact_hash: str
    start_result_id: str
    start_result_hash: str
    launch_attempt_id: str
    launch_attempt_hash: str
    route_id: str
    route_hash: str
    authorization_id: str
    authorization_hash: str
    attempt_id: str
    attempt_hash: str
    task_id: str
    worker_id: str
    worker_version: str
    runtime_run_id: str
    target_state: str
    projected_at: str
    artifact_version: str
    canonical_payload: str
    payload_sha256: str

    def to_canonical_dict(self) -> dict:
        return {
            "schema": "ea4d4b-executing-projection-v1",
            "projection_id": self.projection_id,
            "start_result_id": self.start_result_id,
            "start_result_hash": self.start_result_hash,
            "launch_attempt_id": self.launch_attempt_id,
            "launch_attempt_hash": self.launch_attempt_hash,
            "route_id": self.route_id,
            "route_hash": self.route_hash,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "attempt_id": self.attempt_id,
            "attempt_hash": self.attempt_hash,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "worker_version": self.worker_version,
            "runtime_run_id": self.runtime_run_id,
            "target_state": self.target_state,
            # projected_at intentionally excluded from canonical material payload
        }

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash             and self.payload_sha256 == sha256_text(self.canonical_payload)             and sha256_payload(self.to_canonical_dict()) == sha256_text(
                self.canonical_payload)


def reconstruct_state_projection(payload: Mapping[str, Any]) -> "ExecutionStateProjection":
    """Rebuild an immutable ExecutionStateProjection from a stored mapping."""
    return ExecutionStateProjection(
        projection_id=payload["projection_id"],
        artifact_hash=payload["artifact_hash"],
        start_result_id=payload["start_result_id"],
        start_result_hash=payload["start_result_hash"],
        launch_attempt_id=payload["launch_attempt_id"],
        launch_attempt_hash=payload["launch_attempt_hash"],
        route_id=payload["route_id"],
        route_hash=payload["route_hash"],
        authorization_id=payload["authorization_id"],
        authorization_hash=payload["authorization_hash"],
        attempt_id=payload["attempt_id"],
        attempt_hash=payload["attempt_hash"],
        task_id=payload["task_id"],
        worker_id=payload["worker_id"],
        worker_version=payload["worker_version"],
        runtime_run_id=payload["runtime_run_id"],
        target_state=payload["target_state"],
        projected_at=payload["projected_at"],
        artifact_version=payload.get("artifact_version", PROJECTION_ARTIFACT_VERSION),
        canonical_payload=payload["canonical_payload"],
        payload_sha256=payload["payload_sha256"],
    )
