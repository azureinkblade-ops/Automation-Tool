"""EA-4C.1: WorkerRouter domain + immutable routing artifacts (DOMAIN ONLY).

This module defines the immutable domain artifacts required by the future
WorkerRouter selection layer. It does NOT perform worker eligibility
evaluation or route selection.

It does NOT:

* persist anything (no ``execution_authority.db`` / ``SQLiteExecutionAuthorizationStore``);
* open SQLite or change any schema (EA-4C.1 deliberately avoids persistence);
* implement a routing/transaction service (that is EA-4C.2);
* run concurrency/rollback proofs (that is EA-4C.4);
* evaluate worker eligibility or select a worker (that is EA-4C.3);
* perform any worker execution, process creation, or runtime handoff;
* introduce execution state transitions for the selected worker.

Selection ordering itself is deferred to EA-4C.3. The artifacts here are the
structural, hash-bound types that a later selection layer will operate on.

SYSTEM_ROUTER is NOT a general SYSTEM authority principal. It is a bounded
routing-domain identity whose only permissible EA-4C authority is producing a
deterministic pre-execution route decision. A generic SYSTEM principal never
grants execution authority; SYSTEM_ROUTER is narrower still.

Governing invariants (frozen across EA-4A/EA-4B):

    ACCEPTED != EXECUTION AUTHORIZATION

    ACCEPTED
    != AUTHORIZED
    != CLAIMED
    != EXECUTION_ATTEMPT_RECORDED
    != ROUTE_SELECTED
    != EXECUTING

Design source of truth:
    docs/architecture/HERMES_EA4C_WORKER_ROUTER_DESIGN_AUTHORIZATION.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from .execution_authorization import ExecutionAuthorizationScope
from .hashing import canonical_json, sha256_payload


__all__ = [
    "WorkerRouteError",
    "WorkerRouteNotFoundError",
    "WorkerRouteConflictError",
    "WorkerRouteExpiredError",
    "WorkerRouteIntegrityError",
    "WorkerRouteLineageError",
    "WorkerRouteNoEligibleWorkerError",
    "WorkerRoutePolicyError",
    "WorkerRegistryIntegrityError",
    "WorkerRegistryVersionError",
    "WorkerRouterActorType",
    "WorkerRouterActor",
    "WorkerDescriptor",
    "WorkerRegistry",
    "WorkerRoutingPolicyRef",
    "WorkerRouteStatus",
    "WorkerRouteDecision",
    "ROUTE_ARTIFACT_VERSION",
    "build_worker_descriptor",
    "reconstruct_worker_descriptor",
    "build_worker_registry",
    "reconstruct_worker_registry",
    "build_worker_route_decision",
    "reconstruct_worker_route_decision",
    "verify_worker_route_decision_hash",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class WorkerRouteError(ValueError):
    """Base error for the WorkerRouter domain (EA-4C).

    Domain/structural validation and pure-selection errors only. Persisted-
    tamper integrity exceptions belong to the future EA-4C.2 store layer.
    """


class WorkerRouteNotFoundError(WorkerRouteError):
    """Raised when an expected WorkerRouteDecision does not exist."""


class WorkerRouteConflictError(WorkerRouteError):
    """Raised when a route conflicts with an existing durable route."""


class WorkerRouteExpiredError(WorkerRouteError):
    """Raised when routing is attempted after ``must_start_by``."""


class WorkerRouteIntegrityError(WorkerRouteError):
    """Raised when a route artifact fails hash verification."""


class WorkerRouteLineageError(WorkerRouteError):
    """Raised when route lineage does not match its Attempt/Authorization."""


class WorkerRouteNoEligibleWorkerError(WorkerRouteError):
    """Raised when zero registered workers satisfy the eligibility policy.

    Per EA-4C design resolution A2: this is a NON-PERSISTED typed result. No
    WorkerRouteDecision is created, no ROUTE_SELECTED event is emitted. The
    absence of a route artifact is itself the signal that no deterministic
    selection occurred.
    """


class WorkerRoutePolicyError(WorkerRouteError):
    """Raised when the routing policy reference is invalid or mismatched."""


class WorkerRegistryIntegrityError(WorkerRouteError):
    """Raised when the worker registry fails hash verification."""


class WorkerRegistryVersionError(WorkerRouteError):
    """Raised when the worker registry version is unsupported."""


# --------------------------------------------------------------------------- #
# Router actor (bounded routing-domain identity)
# --------------------------------------------------------------------------- #


class WorkerRouterActorType(str, Enum):
    """Bounded routing-domain actor types.

    SYSTEM_ROUTER is the resolved EA-4C router principal (design decision A1).
    It is NOT a general SYSTEM authority principal and grants no execution
    authority of any kind. POLICY_SERVICE is permitted as an alternative
    bounded routing authority. Neither implies launch/dispatch capability.
    """

    SYSTEM_ROUTER = "SYSTEM_ROUTER"
    POLICY_SERVICE = "POLICY_SERVICE"


@dataclass(frozen=True)
class WorkerRouterActor:
    """Structured identity of the component invoking WorkerRouter.

    This identity represents the bounded routing-domain principal permitted to
    produce a deterministic pre-execution route decision. It does NOT grant
    worker execution authority.
    """

    actor_id: str
    actor_type: WorkerRouterActorType
    actor_context: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "actor_type": self.actor_type.value,
            "actor_context": self.actor_context,
        }


# --------------------------------------------------------------------------- #
# Worker descriptor + registry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkerDescriptor:
    """A registered, structured worker identity.

    Worker identity is NEVER derived from an executable path or free-form
    command string. Selection operates only on registered descriptors.
    """

    worker_id: str
    worker_class: Optional[str]
    worker_version: str
    capabilities: Sequence[str]
    allowed_operations: Sequence[str]
    enabled: bool
    registration_source: str
    registration_version: str
    descriptor_hash: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing (excludes descriptor_hash)."""
        return {
            "worker_id": self.worker_id,
            "worker_class": self.worker_class,
            "worker_version": self.worker_version,
            "capabilities": list(self.capabilities),
            "allowed_operations": list(self.allowed_operations),
            "enabled": self.enabled,
            "registration_source": self.registration_source,
            "registration_version": self.registration_version,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.descriptor_hash


@dataclass(frozen=True)
class WorkerRegistry:
    """Versioned, tamper-evident, fail-closed worker registry snapshot.

    The exact registry snapshot used for routing is bound into the route
    artifact via ``registry_version`` / ``registry_hash``. The registry is
    read-only during route selection.
    """

    registry_version: str
    registry_hash: str
    workers: Sequence[WorkerDescriptor]

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing (excludes registry_hash)."""
        return {
            "registry_version": self.registry_version,
            "workers": [w.to_canonical_dict() for w in self.workers],
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.registry_hash


# --------------------------------------------------------------------------- #
# Routing policy reference
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkerRoutingPolicyRef:
    """Immutable reference to the policy that governed route selection."""

    policy_id: str
    policy_version: str
    policy_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
        }


# --------------------------------------------------------------------------- #
# Route decision artifact
# --------------------------------------------------------------------------- #


class WorkerRouteStatus(str, Enum):
    """Pre-execution routing state only.

    EA-4C deliberately stops at ROUTE_SELECTED. It does NOT introduce
    EXECUTING / RUNNING / STARTED / SUCCEEDED / FAILED / CANCELLED.
    """

    SELECTED = "SELECTED"


ROUTE_ARTIFACT_VERSION = "1"


def _route_id_preimage(
    *,
    attempt_id: str,
    worker_id: str,
    worker_class: Optional[str],
    registry_version: str,
    registry_hash: str,
    policy: WorkerRoutingPolicyRef,
    router_actor: WorkerRouterActor,
) -> dict[str, Any]:
    """Replay-significant identity inputs for a route decision.

    Exact replay (per design packet §14) requires equality of: Attempt ID/hash,
    registry version/hash, routing policy version/hash, selected worker ID/
    class, structured router actor identity. The route_id is derived from
    exactly this set so replay yields identical route_id regardless of clock.
    """
    return {
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "worker_class": worker_class,
        "registry_version": registry_version,
        "registry_hash": registry_hash,
        "routing_policy_id": policy.policy_id,
        "routing_policy_version": policy.policy_version,
        "routing_policy_hash": policy.policy_hash,
        "router_actor_id": router_actor.actor_id,
        "router_actor_type": router_actor.actor_type.value,
        "router_actor_context": router_actor.actor_context,
    }


@dataclass(frozen=True)
class WorkerRouteDecision:
    """Immutable, hash-bound routing decision (EA-4C terminal artifact).

    If this artifact exists, it represents an actual deterministic selection
    and its only state is SELECTED. No eligible worker produces no durable
    route (design resolution A2).
    """

    route_id: str
    artifact_version: str
    artifact_hash: str
    attempt_id: str
    attempt_hash: str
    authorization_id: str
    authorization_hash: str
    claim_id: str
    claim_hash: str
    request_id: str
    request_hash: str
    decision_id: str
    decision_hash: str
    task_id: str
    worker_id: str
    worker_class: Optional[str]
    worker_registry_version: str
    worker_registry_hash: str
    routing_policy_id: str
    routing_policy_version: str
    routing_policy_hash: str
    selected_at: str  # absolute UTC RFC3339/ISO ending Z
    must_start_by: str  # absolute UTC RFC3339/ISO ending Z
    operation: str
    input_hash: str
    router_actor_id: str
    router_actor_type: str
    router_actor_context: Optional[str]
    status: WorkerRouteStatus

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing (excludes artifact_hash)."""
        return {
            "route_id": self.route_id,
            "artifact_version": self.artifact_version,
            "attempt_id": self.attempt_id,
            "attempt_hash": self.attempt_hash,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "claim_id": self.claim_id,
            "claim_hash": self.claim_hash,
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "decision_id": self.decision_id,
            "decision_hash": self.decision_hash,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "worker_class": self.worker_class,
            "worker_registry_version": self.worker_registry_version,
            "worker_registry_hash": self.worker_registry_hash,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "routing_policy_hash": self.routing_policy_hash,
            "selected_at": self.selected_at,
            "must_start_by": self.must_start_by,
            "operation": self.operation,
            "input_hash": self.input_hash,
            "router_actor_id": self.router_actor_id,
            "router_actor_type": self.router_actor_type,
            "router_actor_context": self.router_actor_context,
            "status": self.status.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Builders / reconstructors
# --------------------------------------------------------------------------- #


def build_worker_descriptor(
    *,
    worker_id: str,
    worker_class: Optional[str],
    worker_version: str,
    capabilities: Sequence[str],
    allowed_operations: Sequence[str],
    enabled: bool,
    registration_source: str,
    registration_version: str,
) -> WorkerDescriptor:
    if not worker_id:
        raise WorkerRouteError("worker_id is required")
    descriptor = WorkerDescriptor(
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=worker_version,
        capabilities=list(capabilities),
        allowed_operations=list(allowed_operations),
        enabled=enabled,
        registration_source=registration_source,
        registration_version=registration_version,
        descriptor_hash="",
    )
    descriptor_hash = sha256_payload(descriptor.to_canonical_dict())
    return WorkerDescriptor(
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=worker_version,
        capabilities=list(capabilities),
        allowed_operations=list(allowed_operations),
        enabled=enabled,
        registration_source=registration_source,
        registration_version=registration_version,
        descriptor_hash=descriptor_hash,
    )


def reconstruct_worker_descriptor(payload: Mapping[str, Any]) -> WorkerDescriptor:
    descriptor_hash = payload.get("descriptor_hash")
    if not descriptor_hash:
        descriptor_hash = sha256_payload(
            {
                "worker_id": payload["worker_id"],
                "worker_class": payload.get("worker_class"),
                "worker_version": payload["worker_version"],
                "capabilities": list(payload.get("capabilities", [])),
                "allowed_operations": list(payload.get("allowed_operations", [])),
                "enabled": payload["enabled"],
                "registration_source": payload["registration_source"],
                "registration_version": payload["registration_version"],
            }
        )
    return WorkerDescriptor(
        worker_id=payload["worker_id"],
        worker_class=payload.get("worker_class"),
        worker_version=payload["worker_version"],
        capabilities=list(payload.get("capabilities", [])),
        allowed_operations=list(payload.get("allowed_operations", [])),
        enabled=bool(payload["enabled"]),
        registration_source=payload["registration_source"],
        registration_version=payload["registration_version"],
        descriptor_hash=descriptor_hash,
    )


def build_worker_registry(
    *,
    registry_version: str,
    workers: Sequence[WorkerDescriptor],
) -> WorkerRegistry:
    if not registry_version:
        raise WorkerRouteError("registry_version is required")
    registry = WorkerRegistry(
        registry_version=registry_version,
        registry_hash="",
        workers=list(workers),
    )
    registry_hash = sha256_payload(registry.to_canonical_dict())
    return WorkerRegistry(
        registry_version=registry_version,
        registry_hash=registry_hash,
        workers=list(workers),
    )


def reconstruct_worker_registry(payload: Mapping[str, Any]) -> WorkerRegistry:
    return WorkerRegistry(
        registry_version=payload["registry_version"],
        registry_hash=payload["registry_hash"],
        workers=[
            reconstruct_worker_descriptor(w) for w in payload.get("workers", [])
        ],
    )


def build_worker_route_decision(
    *,
    attempt_id: str,
    attempt_hash: str,
    authorization_id: str,
    authorization_hash: str,
    claim_id: str,
    claim_hash: str,
    request_id: str,
    request_hash: str,
    decision_id: str,
    decision_hash: str,
    task_id: str,
    worker_id: str,
    worker_class: Optional[str],
    registry: WorkerRegistry,
    policy: WorkerRoutingPolicyRef,
    selected_at: str,
    must_start_by: str,
    operation: str,
    input_hash: str,
    router_actor: WorkerRouterActor,
) -> WorkerRouteDecision:
    if not isinstance(router_actor, WorkerRouterActor):
        raise WorkerRouteError("router_actor must be a WorkerRouterActor")
    route_id = sha256_payload(
        _route_id_preimage(
            attempt_id=attempt_id,
            worker_id=worker_id,
            worker_class=worker_class,
            registry_version=registry.registry_version,
            registry_hash=registry.registry_hash,
            policy=policy,
            router_actor=router_actor,
        )
    )
    decision = WorkerRouteDecision(
        route_id=route_id,
        artifact_version=ROUTE_ARTIFACT_VERSION,
        artifact_hash="",
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        claim_id=claim_id,
        claim_hash=claim_hash,
        request_id=request_id,
        request_hash=request_hash,
        decision_id=decision_id,
        decision_hash=decision_hash,
        task_id=task_id,
        worker_id=worker_id,
        worker_class=worker_class,
        worker_registry_version=registry.registry_version,
        worker_registry_hash=registry.registry_hash,
        routing_policy_id=policy.policy_id,
        routing_policy_version=policy.policy_version,
        routing_policy_hash=policy.policy_hash,
        selected_at=selected_at,
        must_start_by=must_start_by,
        operation=operation,
        input_hash=input_hash,
        router_actor_id=router_actor.actor_id,
        router_actor_type=router_actor.actor_type.value,
        router_actor_context=router_actor.actor_context,
        status=WorkerRouteStatus.SELECTED,
    )
    artifact_hash = sha256_payload(decision.to_canonical_dict())
    return WorkerRouteDecision(
        route_id=route_id,
        artifact_version=ROUTE_ARTIFACT_VERSION,
        artifact_hash=artifact_hash,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        claim_id=claim_id,
        claim_hash=claim_hash,
        request_id=request_id,
        request_hash=request_hash,
        decision_id=decision_id,
        decision_hash=decision_hash,
        task_id=task_id,
        worker_id=worker_id,
        worker_class=worker_class,
        worker_registry_version=registry.registry_version,
        worker_registry_hash=registry.registry_hash,
        routing_policy_id=policy.policy_id,
        routing_policy_version=policy.policy_version,
        routing_policy_hash=policy.policy_hash,
        selected_at=selected_at,
        must_start_by=must_start_by,
        operation=operation,
        input_hash=input_hash,
        router_actor_id=router_actor.actor_id,
        router_actor_type=router_actor.actor_type.value,
        router_actor_context=router_actor.actor_context,
        status=WorkerRouteStatus.SELECTED,
    )


def reconstruct_worker_route_decision(
    payload: Mapping[str, Any],
) -> WorkerRouteDecision:
    artifact_hash = payload.get("artifact_hash")
    if not artifact_hash:
        artifact_hash = sha256_payload(
            {
                "route_id": payload["route_id"],
                "artifact_version": payload["artifact_version"],
                "attempt_id": payload["attempt_id"],
                "attempt_hash": payload["attempt_hash"],
                "authorization_id": payload["authorization_id"],
                "authorization_hash": payload["authorization_hash"],
                "claim_id": payload["claim_id"],
                "claim_hash": payload["claim_hash"],
                "request_id": payload["request_id"],
                "request_hash": payload["request_hash"],
                "decision_id": payload["decision_id"],
                "decision_hash": payload["decision_hash"],
                "task_id": payload["task_id"],
                "worker_id": payload["worker_id"],
                "worker_class": payload.get("worker_class"),
                "worker_registry_version": payload["worker_registry_version"],
                "worker_registry_hash": payload["worker_registry_hash"],
                "routing_policy_id": payload["routing_policy_id"],
                "routing_policy_version": payload["routing_policy_version"],
                "routing_policy_hash": payload["routing_policy_hash"],
                "selected_at": payload["selected_at"],
                "must_start_by": payload["must_start_by"],
                "operation": payload["operation"],
                "input_hash": payload["input_hash"],
                "router_actor_id": payload["router_actor_id"],
                "router_actor_type": payload["router_actor_type"],
                "router_actor_context": payload.get("router_actor_context"),
                "status": payload["status"],
            }
        )
    return WorkerRouteDecision(
        route_id=payload["route_id"],
        artifact_version=payload["artifact_version"],
        artifact_hash=artifact_hash,
        attempt_id=payload["attempt_id"],
        attempt_hash=payload["attempt_hash"],
        authorization_id=payload["authorization_id"],
        authorization_hash=payload["authorization_hash"],
        claim_id=payload["claim_id"],
        claim_hash=payload["claim_hash"],
        request_id=payload["request_id"],
        request_hash=payload["request_hash"],
        decision_id=payload["decision_id"],
        decision_hash=payload["decision_hash"],
        task_id=payload["task_id"],
        worker_id=payload["worker_id"],
        worker_class=payload.get("worker_class"),
        worker_registry_version=payload["worker_registry_version"],
        worker_registry_hash=payload["worker_registry_hash"],
        routing_policy_id=payload["routing_policy_id"],
        routing_policy_version=payload["routing_policy_version"],
        routing_policy_hash=payload["routing_policy_hash"],
        selected_at=payload["selected_at"],
        must_start_by=payload["must_start_by"],
        operation=payload["operation"],
        input_hash=payload["input_hash"],
        router_actor_id=payload["router_actor_id"],
        router_actor_type=payload["router_actor_type"],
        router_actor_context=payload.get("router_actor_context"),
        status=WorkerRouteStatus(payload["status"]),
    )


def verify_worker_route_decision_hash(decision: WorkerRouteDecision) -> bool:
    return decision.verify_hash()
