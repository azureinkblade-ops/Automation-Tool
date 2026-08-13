"""Immutable domain model for Hermes execution authorization (EA-1).

This module defines the *structural* domain artifacts only. It does NOT:

* persist anything (no ``execution_authority.db`` / ``SQLiteExecutionAuthorizationStore``);
* issue, consume, or revoke authorizations (no issuance service);
* implement ``ExecutionClaim`` / ``ExecutionAttempt``;
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

from .hashing import canonical_json, sha256_payload

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
SUPPORTED_ARTIFACT_VERSIONS = frozenset({"1", "2"})
AMENDED_ARTIFACT_VERSION = "2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORIZATION_ID_RE = re.compile(r"^execution-authorization-[0-9a-f]{16}$")
_REQUEST_ID_RE = re.compile(r"^execution-authorization-request-[0-9a-f]{16}$")
_DECISION_ID_RE = re.compile(r"^execution-authorization-decision-[0-9a-f]{16}$")

_ID_PREFIX = "execution-authorization-"
_REQUEST_ID_PREFIX = "execution-authorization-request-"
_DECISION_ID_PREFIX = "execution-authorization-decision-"


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
# Builders (pure constructors; zero authority semantics)
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
