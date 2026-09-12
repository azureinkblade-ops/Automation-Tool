"""EA-4D.1: Execution Start Boundary -- DOMAIN ARTIFACTS ONLY.

This module defines the immutable domain artifacts for the EA-4D execution-start
boundary: the start reservation, the launch attempt, the start result, the
launcher actor, and the runtime binding. It is the first EA-4D slice and it is
strictly DOMAIN-ONLY.

It does NOT:
* persist anything (no ``execution_authority.db`` / ``SQLiteExecutionAuthorizationStore``);
* open SQLite or change any schema (that is EA-4D.2);
* implement a start-reservation service (EA-4D.2);
* implement launch-attempt persistence or external worker invocation (EA-4D.3);
* implement concurrency / crash-ambiguity proofs (EA-4D.4);
* wire into scheduler / application / web / worker processes (EA-4D.5);
* perform any subprocess, process creation, or network call;
* introduce or transition any execution state (no ``EXECUTING`` transition exists).

The full EA-4D state path is frozen in the design document:

    ROUTE_SELECTED
        -> START_RESERVED
        -> LAUNCH_ATTEMPT_RECORDED
        -> EXECUTING

EA-4D.1 defines the structural, hash-bound types only. It does not record any
of those transitions.

Governing invariant (frozen across EA-4A/EA-4B/EA-4C):

    ACCEPTED != AUTHORIZED != CLAIMED != EXECUTION_ATTEMPT_RECORDED
             != ROUTE_SELECTED != START_RESERVED != LAUNCH_ATTEMPT_RECORDED
             != EXECUTING

Each state is independently meaningful; no earlier state implies a worker started.

SYSTEM_ROUTER != SYSTEM_LAUNCHER. Selecting a worker (EA-4C) does not grant
runtime launch identity. Initial automated start ownership is limited to
``SYSTEM_LAUNCHER``.

Runtime bindings are domain metadata only: they may identify an adapter
symbolically (e.g. ``adapter_kind = "LOCAL_WORKER_ADAPTER"``) but contain no
executable object, callable, shell command, or network endpoint, and they never
execute anything in EA-4D.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from .hashing import canonical_json, sha256_payload


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class ExecutionStartReservationStatus(str, Enum):
    """EA-4D.1 authorized status for a start reservation.

    Only RESERVED is authorized in EA-4D.1. No further status transitions are
    defined at the domain layer in this slice.
    """

    RESERVED = "RESERVED"


class ExecutionLaunchAttemptStatus(str, Enum):
    """EA-4D.1 authorized status for a launch attempt.

    RECORDED explicitly means: the single permitted external launch attempt was
    durably admitted, but the worker is NOT proven started.
    """

    RECORDED = "RECORDED"


class ExecutionStartOutcome(str, Enum):
    """Allowed execution-start outcomes (recorded by a later EA-4D slice)."""

    STARTED = "STARTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ExecutionLauncherActorType(str, Enum):
    """Bounded EA-4D launcher principal.

    SYSTEM_LAUNCHER is the only initial automated start-ownership identity.
    A generic SYSTEM principal never grants launch rights, and SYSTEM_ROUTER
    (EA-4C) never launches.
    """

    SYSTEM_LAUNCHER = "SYSTEM_LAUNCHER"


class WorkerRuntimeAdapterKind(str, Enum):
    """Symbolic adapter kinds (no executable contract in EA-4D.1).

    The exact initial adapter set is frozen before launch implementation
    (EA-4D.3). These values are identifiers only.
    """

    LOCAL_WORKER_ADAPTER = "LOCAL_WORKER_ADAPTER"
    MODEL_RUNTIME_ADAPTER = "MODEL_RUNTIME_ADAPTER"
    HTTP_WORKER_ADAPTER = "HTTP_WORKER_ADAPTER"


# --------------------------------------------------------------------------- #
# Errors (domain, derived from a single base)
# --------------------------------------------------------------------------- #


class ExecutionStartError(Exception):
    """Base domain error for EA-4D start-boundary artifacts."""


class ExecutionStartNotFoundError(ExecutionStartError):
    """Referenced start/reservation entity not found."""


class ExecutionStartIntegrityError(ExecutionStartError):
    """Structural or hash integrity violation on a start-boundary artifact."""


class ExecutionStartLineageError(ExecutionStartError):
    """Lineage binding mismatch across ancestor artifacts."""


class ExecutionStartExpiredError(ExecutionStartError):
    """Start attempted after the must_start_by deadline (fail-closed)."""


class ExecutionStartConflictError(ExecutionStartError):
    """Replay-significant divergence for an already-reserved route."""


class ExecutionRuntimeBindingError(ExecutionStartError):
    """Base error for runtime binding resolution."""


class ExecutionRuntimeBindingNotFoundError(ExecutionRuntimeBindingError):
    """Selected worker has no exact enabled runtime binding (fail-closed)."""


class ExecutionRuntimeBindingIntegrityError(ExecutionRuntimeBindingError):
    """Runtime binding structural or hash integrity violation."""


class ExecutionRuntimeBindingMismatchError(ExecutionRuntimeBindingError):
    """Runtime binding does not exactly match worker identity/operation."""


class ExecutionLaunchAttemptError(ExecutionStartError):
    """Base error for launch-attempt artifacts."""


class ExecutionLaunchAttemptConflictError(ExecutionLaunchAttemptError):
    """More than one launch attempt for a single reservation (invariant)."""


class ExecutionStartResultError(ExecutionStartError):
    """Base error for start-result artifacts."""


class ExecutionStartResultConflictError(ExecutionStartResultError):
    """Conflicting ExecutionStartResult for the same launch attempt (fail closed)."""


# --------------------------------------------------------------------------- #
# Actors
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionLauncherActor:
    """Bounded EA-4D launcher principal (separate from SYSTEM_ROUTER)."""

    actor_id: str
    actor_type: ExecutionLauncherActorType
    actor_context: Optional[str] = None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "actor_type": self.actor_type.value,
            "actor_context": self.actor_context,
        }


# --------------------------------------------------------------------------- #
# Artifact 1: ExecutionStartReservation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionStartReservation:
    """Immutable, hash-bound start reservation (EA-4D terminal authorized artifact).

    A reservation grants the exclusive right to attempt execution start for one
    WorkerRouteDecision. It does NOT mean the worker was invoked, a process
    exists, or work began.
    """

    reservation_id: str
    artifact_version: str
    artifact_hash: str
    route_id: str
    route_hash: str
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
    worker_version: str
    operation: str
    input_hash: str
    reserved_at: str  # absolute UTC RFC3339/ISO ending Z
    must_start_by: str  # absolute UTC RFC3339/ISO ending Z
    launcher_actor_id: str
    launcher_actor_type: str
    launcher_actor_context: Optional[str]
    status: ExecutionStartReservationStatus

    def to_canonical_dict(self) -> dict[str, Any]:
        """Deterministic preimage for hashing (excludes artifact_hash)."""
        return {
            "reservation_id": self.reservation_id,
            "artifact_version": self.artifact_version,
            "route_id": self.route_id,
            "route_hash": self.route_hash,
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
            "worker_version": self.worker_version,
            "operation": self.operation,
            "input_hash": self.input_hash,
            "reserved_at": self.reserved_at,
            "must_start_by": self.must_start_by,
            "launcher_actor_id": self.launcher_actor_id,
            "launcher_actor_type": self.launcher_actor_type,
            "launcher_actor_context": self.launcher_actor_context,
            "status": self.status.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Artifact 2: ExecutionLaunchAttempt
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionLaunchAttempt:
    """Immutable, hash-bound launch attempt (EA-4D.1 may define, must NOT persist/launch).

    RECORDED means the single permitted external launch attempt was durably
    admitted BEFORE the external side effect; the worker is not proven started.
    """

    launch_attempt_id: str
    launch_attempt_version: str
    artifact_hash: str
    reservation_id: str
    reservation_hash: str
    route_id: str
    route_hash: str
    attempt_id: str
    attempt_hash: str
    authorization_id: str
    authorization_hash: str
    task_id: str
    worker_id: str
    worker_class: Optional[str]
    worker_version: str
    operation: str
    input_hash: str
    runtime_binding_id: str
    runtime_binding_version: str
    runtime_binding_hash: str
    idempotency_key: str
    recorded_at: str  # absolute UTC RFC3339/ISO ending Z
    must_start_by: str  # absolute UTC RFC3339/ISO ending Z
    launcher_actor_id: str
    launcher_actor_type: str
    launcher_actor_context: Optional[str]
    status: ExecutionLaunchAttemptStatus

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "launch_attempt_id": self.launch_attempt_id,
            "launch_attempt_version": self.launch_attempt_version,
            "reservation_id": self.reservation_id,
            "reservation_hash": self.reservation_hash,
            "route_id": self.route_id,
            "route_hash": self.route_hash,
            "attempt_id": self.attempt_id,
            "attempt_hash": self.attempt_hash,
            "authorization_id": self.authorization_id,
            "authorization_hash": self.authorization_hash,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "worker_class": self.worker_class,
            "worker_version": self.worker_version,
            "operation": self.operation,
            "input_hash": self.input_hash,
            "runtime_binding_id": self.runtime_binding_id,
            "runtime_binding_version": self.runtime_binding_version,
            "runtime_binding_hash": self.runtime_binding_hash,
            "idempotency_key": self.idempotency_key,
            "recorded_at": self.recorded_at,
            "must_start_by": self.must_start_by,
            "launcher_actor_id": self.launcher_actor_id,
            "launcher_actor_type": self.launcher_actor_type,
            "launcher_actor_context": self.launcher_actor_context,
            "status": self.status.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Artifact 3: ExecutionStartResult
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionStartResult:
    """Immutable, hash-bound start result (EA-4D.1 may define; EA-4D.4A persists).

    Persisted result semantics are a distinct governance stage from runtime
    adapter outcome. The result is immutable after insert. ``error_summary`` is
    non-identity, integrity-bound persisted metadata (see build + artifact hash).
    """

    start_result_id: str
    start_result_version: str
    artifact_hash: str
    launch_attempt_id: str
    launch_attempt_hash: str
    reservation_id: str
    reservation_hash: str
    route_id: str
    route_hash: str
    task_id: str
    worker_id: str
    worker_version: str
    runtime_binding_id: str
    runtime_binding_version: str
    runtime_binding_hash: str
    idempotency_key: str
    outcome: ExecutionStartOutcome
    recorded_at: str  # absolute UTC RFC3339/ISO ending Z
    runtime_run_id: Optional[str] = None
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    runtime_evidence_hash: Optional[str] = None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "start_result_id": self.start_result_id,
            "start_result_version": self.start_result_version,
            "launch_attempt_id": self.launch_attempt_id,
            "launch_attempt_hash": self.launch_attempt_hash,
            "reservation_id": self.reservation_id,
            "reservation_hash": self.reservation_hash,
            "route_id": self.route_id,
            "route_hash": self.route_hash,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "worker_version": self.worker_version,
            "runtime_binding_id": self.runtime_binding_id,
            "runtime_binding_version": self.runtime_binding_version,
            "runtime_binding_hash": self.runtime_binding_hash,
            "idempotency_key": self.idempotency_key,
            "outcome": self.outcome.value,
            "recorded_at": self.recorded_at,
            "runtime_run_id": self.runtime_run_id,
            "runtime_evidence_hash": self.runtime_evidence_hash,
            "error_code": self.error_code,
            "error_summary": self.error_summary,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Runtime binding (domain metadata ONLY in EA-4D.1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkerRuntimeBinding:
    """Symbolic runtime binding metadata (NO executable object/callable in EA-4D.1).

    Maps a selected worker identity to a trusted typed runtime adapter. It must
    not contain a shell command, process spec, or network endpoint, and it never
    executes anything in this slice.
    """

    runtime_binding_id: str
    runtime_binding_version: str
    artifact_hash: str
    worker_id: str
    worker_version: str
    worker_class: Optional[str]
    adapter_kind: WorkerRuntimeAdapterKind
    adapter_version: str
    configuration_reference: str
    configuration_hash: str
    allowed_operations: List[str] = field(default_factory=list)
    supports_idempotency: bool = False
    enabled: bool = True

    def to_canonical_dict(self) -> dict[str, Any]:
        # Canonicalize operation set deterministically (sorted, deduped).
        ops = sorted(set(self.allowed_operations))
        return {
            "runtime_binding_id": self.runtime_binding_id,
            "runtime_binding_version": self.runtime_binding_version,
            "worker_id": self.worker_id,
            "worker_version": self.worker_version,
            "worker_class": self.worker_class,
            "adapter_kind": self.adapter_kind.value,
            "adapter_version": self.adapter_version,
            "configuration_reference": self.configuration_reference,
            "configuration_hash": self.configuration_hash,
            "allowed_operations": ops,
            "supports_idempotency": self.supports_idempotency,
            "enabled": self.enabled,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Builders (pure: normalize, validate, hash; no persistence / system / network)
# --------------------------------------------------------------------------- #


def _finalize(cls, partial):
    """Compute immutable artifact_hash and return a fully-built frozen artifact."""
    artifact_hash = sha256_payload(partial.to_canonical_dict())
    return cls(artifact_hash=artifact_hash,
               **{k: v for k, v in partial.__dict__.items() if k != "artifact_hash"})


def build_execution_start_reservation(
    *,
    reservation_id: str,
    route_id: str,
    route_hash: str,
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
    worker_version: str,
    operation: str,
    input_hash: str,
    reserved_at: str,
    must_start_by: str,
    launcher_actor: ExecutionLauncherActor,
    artifact_version: str = "1",
    status: ExecutionStartReservationStatus = ExecutionStartReservationStatus.RESERVED,
) -> ExecutionStartReservation:
    """Build a hash-bound ExecutionStartReservation (no persistence)."""
    if not reservation_id:
        raise ExecutionStartIntegrityError("reservation_id is required")
    if not route_id or not route_hash:
        raise ExecutionStartIntegrityError("route_id and route_hash are required")
    if not attempt_id or not attempt_hash:
        raise ExecutionStartLineageError("attempt_id/hash is required for lineage binding")
    if launcher_actor.actor_type != ExecutionLauncherActorType.SYSTEM_LAUNCHER:
        raise ExecutionStartIntegrityError(
            f"only {ExecutionLauncherActorType.SYSTEM_LAUNCHER.value} may reserve start; "
            f"got {launcher_actor.actor_type.value}")
    if status != ExecutionStartReservationStatus.RESERVED:
        raise ExecutionStartIntegrityError(
            f"EA-4D.1 only authorizes status RESERVED; got {getattr(status, 'value', status)!r}")
    partial = ExecutionStartReservation(
        reservation_id=reservation_id,
        artifact_version=artifact_version,
        artifact_hash="",
        route_id=route_id,
        route_hash=route_hash,
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
        worker_version=worker_version,
        operation=operation,
        input_hash=input_hash,
        reserved_at=reserved_at,
        must_start_by=must_start_by,
        launcher_actor_id=launcher_actor.actor_id,
        launcher_actor_type=launcher_actor.actor_type.value,
        launcher_actor_context=launcher_actor.actor_context,
        status=status,
    )
    return _finalize(ExecutionStartReservation, partial)


def build_execution_launch_attempt(
    *,
    launch_attempt_id: str,
    reservation_id: str,
    reservation_hash: str,
    route_id: str,
    route_hash: str,
    attempt_id: str,
    attempt_hash: str,
    authorization_id: str,
    authorization_hash: str,
    task_id: str,
    worker_id: str,
    worker_class: Optional[str],
    worker_version: str,
    operation: str,
    input_hash: str,
    runtime_binding_id: str,
    runtime_binding_version: str,
    runtime_binding_hash: str,
    idempotency_key: str,
    recorded_at: str,
    must_start_by: str,
    launcher_actor: ExecutionLauncherActor,
    artifact_version: str = "1",
    status: ExecutionLaunchAttemptStatus = ExecutionLaunchAttemptStatus.RECORDED,
) -> ExecutionLaunchAttempt:
    """Build a hash-bound ExecutionLaunchAttempt (no persistence, no launch)."""
    if not launch_attempt_id:
        raise ExecutionLaunchAttemptError("launch_attempt_id is required")
    if not reservation_id or not reservation_hash:
        raise ExecutionLaunchAttemptError("reservation_id/hash is required")
    if launcher_actor.actor_type != ExecutionLauncherActorType.SYSTEM_LAUNCHER:
        raise ExecutionStartIntegrityError(
            f"only {ExecutionLauncherActorType.SYSTEM_LAUNCHER.value} may launch; "
            f"got {launcher_actor.actor_type.value}")
    if status != ExecutionLaunchAttemptStatus.RECORDED:
        raise ExecutionLaunchAttemptError(
            f"EA-4D.1 only authorizes status RECORDED; got {status.value}")
    partial = ExecutionLaunchAttempt(
        launch_attempt_id=launch_attempt_id,
        launch_attempt_version=artifact_version,
        artifact_hash="",
        reservation_id=reservation_id,
        reservation_hash=reservation_hash,
        route_id=route_id,
        route_hash=route_hash,
        attempt_id=attempt_id,
        attempt_hash=attempt_hash,
        authorization_id=authorization_id,
        authorization_hash=authorization_hash,
        task_id=task_id,
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=worker_version,
        operation=operation,
        input_hash=input_hash,
        runtime_binding_id=runtime_binding_id,
        runtime_binding_version=runtime_binding_version,
        runtime_binding_hash=runtime_binding_hash,
        idempotency_key=idempotency_key,
        recorded_at=recorded_at,
        must_start_by=must_start_by,
        launcher_actor_id=launcher_actor.actor_id,
        launcher_actor_type=launcher_actor.actor_type.value,
        launcher_actor_context=launcher_actor.actor_context,
        status=status,
    )
    return _finalize(ExecutionLaunchAttempt, partial)


def build_execution_start_result(
    *,
    launch_attempt_id: str,
    launch_attempt_hash: str,
    reservation_id: str,
    reservation_hash: str,
    route_id: str,
    route_hash: str,
    task_id: str,
    worker_id: str,
    worker_version: str,
    runtime_binding_id: Optional[str] = None,
    runtime_binding_version: Optional[str] = None,
    runtime_binding_hash: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    outcome: ExecutionStartOutcome,
    recorded_at: str,
    runtime_evidence_hash: Optional[str] = None,
    runtime_run_id: Optional[str] = None,
    error_code: Optional[str] = None,
    error_summary: Optional[str] = None,
    start_result_id: Optional[str] = None,
    artifact_version: str = "1",
) -> ExecutionStartResult:
    """Build a hash-bound ExecutionStartResult (no persistence, no emission).

    EA-4D.4A frozen rules:
    - ``start_result_id`` is deterministic: full SHA-256 over
      ``{"schema": "ea4d4-start-result-id-v1", "launch_attempt_id": ...}``
      using the repository ``canonical_json`` + ``sha256_payload`` convention.
      Any ``start_result_id`` argument is overridden by the derived identity
      (caller may not choose/override result identity).
    - STARTED requires a non-empty ``runtime_run_id`` AND ``runtime_evidence_hash``.
    - FAILED requires an ``error_code`` (definitive non-start).
    - ``error_summary`` is non-identity, integrity-bound metadata.
    """
    if outcome not in (ExecutionStartOutcome.STARTED, ExecutionStartOutcome.FAILED,
                        ExecutionStartOutcome.UNKNOWN):
        raise ExecutionStartResultError(f"invalid outcome: {outcome!r}")
    derived_id = sha256_payload({
        "schema": "ea4d4-start-result-id-v1",
        "launch_attempt_id": launch_attempt_id,
    })
    partial = ExecutionStartResult(
        start_result_id=derived_id,
        start_result_version=artifact_version,
        artifact_hash="",
        launch_attempt_id=launch_attempt_id,
        launch_attempt_hash=launch_attempt_hash,
        reservation_id=reservation_id,
        reservation_hash=reservation_hash,
        route_id=route_id,
        route_hash=route_hash,
        task_id=task_id,
        worker_id=worker_id,
        worker_version=worker_version,
        runtime_binding_id=runtime_binding_id,
        runtime_binding_version=runtime_binding_version,
        runtime_binding_hash=runtime_binding_hash,
        idempotency_key=idempotency_key,
        outcome=outcome,
        recorded_at=recorded_at,
        runtime_run_id=runtime_run_id,
        error_code=error_code,
        error_summary=error_summary,
        runtime_evidence_hash=runtime_evidence_hash,
    )
    return _finalize(ExecutionStartResult, partial)


def build_worker_runtime_binding(
    *,
    runtime_binding_id: str,
    worker_id: str,
    worker_version: str,
    worker_class: Optional[str],
    adapter_kind: WorkerRuntimeAdapterKind,
    adapter_version: str,
    configuration_reference: str,
    configuration_hash: str,
    allowed_operations: Optional[List[str]] = None,
    supports_idempotency: bool = False,
    enabled: bool = True,
    artifact_version: str = "1",
) -> WorkerRuntimeBinding:
    """Build a symbolic runtime binding (domain metadata only; never executes)."""
    if not runtime_binding_id:
        raise ExecutionRuntimeBindingIntegrityError("runtime_binding_id is required")
    # Canonicalize operation set once (stored field matches the canonical preimage).
    ops = sorted(set(allowed_operations or []))
    partial = WorkerRuntimeBinding(
        runtime_binding_id=runtime_binding_id,
        runtime_binding_version=artifact_version,
        artifact_hash="",
        worker_id=worker_id,
        worker_version=worker_version,
        worker_class=worker_class,
        adapter_kind=adapter_kind,
        adapter_version=adapter_version,
        configuration_reference=configuration_reference,
        configuration_hash=configuration_hash,
        allowed_operations=ops,
        supports_idempotency=supports_idempotency,
        enabled=enabled,
    )
    return _finalize(WorkerRuntimeBinding, partial)
