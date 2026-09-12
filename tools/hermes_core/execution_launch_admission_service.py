"""EA-4D.3B execution-launch admission service.

Durable launch-attempt admission: loads a verified START_RESERVED reservation,
independently loads/verifies Route, Attempt, Authorization, resolves an exact
trusted runtime binding (via EA-4D.3A), builds and persists exactly one
ExecutionLaunchAttempt, appends one LAUNCH_ATTEMPT_RECORDED ledger event, and
returns the durable attempt.

STOPS at LAUNCH_ATTEMPT_RECORDED. Does NOT invoke any adapter or worker.
"""

from __future__ import annotations

from typing import Optional

from tools.hermes_core.execution_authorization import ExecutionAttemptStatus
from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    ExecutionLaunchAttemptConflictError,
    ExecutionLaunchAttemptError,
    ExecutionLaunchAttemptStatus,
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionStartReservationStatus,
    build_execution_launch_attempt,
)
from tools.hermes_core.execution_start_service import (
    ExecutionStartIntegrityError,
    ExecutionStartLineageError,
    ExecutionStartServiceError,
    _capture_clock,
    _require_equal,
)
from tools.hermes_core.runtime_binding_registry import (
    ExecutionRuntimeBindingDisabledError,
    ExecutionRuntimeBindingIdempotencyRequiredError,
    ExecutionRuntimeBindingIntegrityError,
    ExecutionRuntimeBindingNotFoundError,
    ExecutionRuntimeBindingMismatchError,
    ExecutionRuntimeBindingRegistryError,
    resolve_worker_runtime_binding,
    WorkerRuntimeBindingRegistry,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    ExecutionAuthorizationStoreError,
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import (
    ExecutionStartExpiredError,
    ExecutionStartStoreError,
    SQLiteExecutionStartStore,
    _deadline_ok,
)
from tools.hermes_core.worker_router import (
    WorkerRouteDecision,
    WorkerRouteStatus,
)


# --------------------------------------------------------------------------- #
# Canonical EA-4D.3 idempotency key (frozen preimage)
# --------------------------------------------------------------------------- #


def _canonical_idempotency_key(
    *,
    launch_attempt_id: str,
    reservation_id: str,
    reservation_hash: str,
    route_id: str,
    route_hash: str,
) -> str:
    """SHA256(
        UTF8("ea4d3-launch-v1")
        || 0x00
        || UTF8(launch_attempt_id)
        || 0x00
        || UTF8(reservation_id)
        || 0x00
        || UTF8(reservation_hash)
        || 0x00
        || UTF8(route_id)
        || 0x00
        || UTF8(route_hash)
    )

    Deterministic. Not caller-supplied. Not random. Stable for the same
    launch_attempt_id + lineage. Different launch_attempt_id -> different key.
    Different reservation/route lineage -> different key. No circular dependency
    on ExecutionLaunchAttempt.artifact_hash.
    """
    from tools.hermes_core.hashing import sha256_text
    payload = (
        "ea4d3-launch-v1"
        "\0"
        + launch_attempt_id
        + "\0"
        + reservation_id
        + "\0"
        + reservation_hash
        + "\0"
        + route_id
        + "\0"
        + route_hash
    )
    return sha256_text(payload)


# --------------------------------------------------------------------------- #
# Service: admit one durable launch attempt (STOP at LAUNCH_ATTEMPT_RECORDED)
# --------------------------------------------------------------------------- #


def admit_execution_launch_attempt(
    *,
    authority_store: SQLiteExecutionAuthorizationStore,
    start_store: SQLiteExecutionStartStore,
    binding_registry: WorkerRuntimeBindingRegistry,
    reservation_id: str,
    launcher_actor: ExecutionLauncherActor,
    clock: Optional[object] = None,
) -> ExecutionLaunchAttempt:
    """Admit exactly one durable ExecutionLaunchAttempt for a verified
    START_RESERVED reservation.

    Ordering (EA-4D.3 design section 10):
        1. load verified START_RESERVED
        2. require RESERVED
        3. load verified Route
        4. load verified Attempt
        5. load verified Authorization
        6. verify complete lineage
        7. resolve exact trusted runtime binding (EA-4D.3A)
        8. capture UTC now once
        9. recheck must_start_by (inclusive)
        10. determine LaunchAttempt identity (deterministic, stable for replay)
        11. derive canonical idempotency key
        12. build immutable ExecutionLaunchAttempt
        13. persist launch attempt  (record_launch_attempt inside start_store)
        14. append LAUNCH_ATTEMPT_RECORDED
        15. COMMIT
        16. return LaunchAttempt
        17. STOP

    There is NO step 18 that invokes anything.
    """
    if not reservation_id:
        raise ExecutionStartServiceError("reservation_id is required")
    if launcher_actor.actor_type != ExecutionLauncherActorType.SYSTEM_LAUNCHER:
        raise ExecutionStartServiceError(
            f"only {ExecutionLauncherActorType.SYSTEM_LAUNCHER.value} may "
            f"admit a launch attempt")

    # 1-2. load verified START_RESERVED
    try:
        reservation = start_store.get_reservation(reservation_id)
    except Exception as exc:
        raise ExecutionStartServiceError(
            f"could not load reservation {reservation_id}: {exc}") from exc
    if reservation is None:
        raise ExecutionStartLineageError(
            f"reservation {reservation_id} not found in start DB")
    if reservation.status != ExecutionStartReservationStatus.RESERVED:
        raise ExecutionStartIntegrityError(
            f"launch admission requires RESERVED; got {reservation.status}")

    # 3. load + verify Route (authoritative EA-4C read)
    try:
        route = authority_store.get_route_for_attempt(reservation.attempt_id)
    except ExecutionAuthorizationStoreError as exc:
        raise ExecutionStartIntegrityError(
            f"could not load route for attempt "
            f"{reservation.attempt_id}: {exc}") from exc
    if route is None:
        raise ExecutionStartLineageError(
            f"attempt {reservation.attempt_id} has no ROUTE_SELECTED")
    if not isinstance(route, WorkerRouteDecision):
        raise ExecutionStartIntegrityError(
            "loaded object is not a WorkerRouteDecision")
    if not route.verify_hash():
        raise ExecutionStartIntegrityError(
            f"route for attempt {reservation.attempt_id} failed hash verification")
    if route.status != WorkerRouteStatus.SELECTED:
        raise ExecutionStartIntegrityError(
            f"route for attempt {reservation.attempt_id} is not SELECTED "
            f"(status={route.status})")

    # 4. load + verify Attempt (authority store read verifies hash + linkage)
    attempt = authority_store.get_attempt(reservation.attempt_id)
    if attempt is None:
        raise ExecutionStartLineageError(
            f"attempt {reservation.attempt_id} not found in authority store")
    if attempt.status != ExecutionAttemptStatus.RECORDED:
        raise ExecutionStartIntegrityError(
            f"attempt {reservation.attempt_id} is not RECORDED "
            f"(status={attempt.status})")

    # 5. load + verify Authorization
    authorization = authority_store.get_authorization(attempt.authorization_id)
    if authorization is None:
        raise ExecutionStartLineageError(
            f"authorization {attempt.authorization_id} not found")

    # 6. verify complete lineage (reservation <-> route <-> attempt <->
    #    authorization), exactly as required by EA-4D.3B section 7.
    # reservation <-> route
    _require_equal("reservation.route_id", reservation.route_id, route.route_id)
    _require_equal("reservation.route_hash", reservation.route_hash,
                   route.artifact_hash)
    _require_equal("reservation.task_id", reservation.task_id, route.task_id)
    _require_equal("reservation.operation", reservation.operation, route.operation)
    _require_equal("reservation.input_hash", reservation.input_hash, route.input_hash)
    _require_equal("reservation.must_start_by", reservation.must_start_by,
                   route.must_start_by)

    # reservation <-> attempt
    _require_equal("reservation.attempt_id", reservation.attempt_id,
                   attempt.attempt_id)
    _require_equal("reservation.attempt_hash", reservation.attempt_hash,
                   attempt.artifact_hash)
    _require_equal("reservation.claim_id", reservation.claim_id, attempt.claim_id)
    _require_equal("reservation.claim_hash", reservation.claim_hash,
                   attempt.claim_hash)
    _require_equal("reservation.request_id", reservation.request_id,
                   attempt.request_id)
    _require_equal("reservation.request_hash", reservation.request_hash,
                   attempt.request_hash)
    _require_equal("reservation.decision_id", reservation.decision_id,
                   attempt.decision_id)
    _require_equal("reservation.decision_hash", reservation.decision_hash,
                   attempt.decision_hash)
    _require_equal("reservation.task_id", reservation.task_id, attempt.task_id)
    _require_equal("reservation.operation", reservation.operation, attempt.operation)
    _require_equal("reservation.input_hash", reservation.input_hash, attempt.input_hash)
    _require_equal("reservation.must_start_by", reservation.must_start_by,
                   attempt.must_start_by)

    # reservation <-> authorization
    _require_equal("reservation.authorization_id", reservation.authorization_id,
                   authorization.authorization_id)
    _require_equal("reservation.authorization_hash", reservation.authorization_hash,
                   authorization.artifact_hash)

    # route <-> attempt (redundant lineage check, required by section 7)
    _require_equal("route.attempt_id", route.attempt_id, attempt.attempt_id)
    _require_equal("route.attempt_hash", route.attempt_hash, attempt.artifact_hash)
    _require_equal("route.claim_id", route.claim_id, attempt.claim_id)
    _require_equal("route.claim_hash", route.claim_hash, attempt.claim_hash)
    _require_equal("route.request_id", route.request_id, attempt.request_id)
    _require_equal("route.request_hash", route.request_hash, attempt.request_hash)
    _require_equal("route.decision_id", route.decision_id, attempt.decision_id)
    _require_equal("route.decision_hash", route.decision_hash, attempt.decision_hash)
    _require_equal("route.task_id", route.task_id, attempt.task_id)
    _require_equal("route.operation", route.operation, attempt.operation)
    _require_equal("route.input_hash", route.input_hash, attempt.input_hash)

    # route <-> authorization
    _require_equal("route.authorization_id", route.authorization_id,
                   authorization.authorization_id)
    _require_equal("route.authorization_hash", route.authorization_hash,
                   authorization.artifact_hash)

    # attempt <-> authorization
    _require_equal("attempt.authorization_id", attempt.authorization_id,
                   authorization.authorization_id)
    _require_equal("attempt.authorization_hash", attempt.authorization_hash,
                   authorization.artifact_hash)

    # 7. resolve exact trusted runtime binding (EA-4D.3A)
    # Inputs MUST derive from the verified Route/Attempt. No caller-supplied
    # alternate worker identity.
    worker_id = route.worker_id
    worker_version = reservation.worker_version
    worker_class = route.worker_class
    operation = attempt.operation
    try:
        binding = resolve_worker_runtime_binding(
            registry=binding_registry,
            worker_id=worker_id,
            worker_version=worker_version,
            worker_class=worker_class,
            operation=operation,
        )
    except (ExecutionRuntimeBindingDisabledError,
            ExecutionRuntimeBindingIdempotencyRequiredError,
            ExecutionRuntimeBindingNotFoundError,
            ExecutionRuntimeBindingMismatchError,
            ExecutionRuntimeBindingRegistryError,
            ExecutionRuntimeBindingIntegrityError) as exc:
        raise ExecutionStartLineageError(
            f"runtime binding resolution failed for "
            f"worker_id={worker_id}, worker_version={worker_version}, "
            f"worker_class={worker_class}, operation={operation}: {exc}") from exc

    # 8. capture UTC now once
    now = _capture_clock(clock)

    # 9. recheck must_start_by (authoritative from verified Attempt; inclusive)
    if not _deadline_ok(now, attempt.must_start_by):
        raise ExecutionStartExpiredError(
            f"launch admission denied: now={now} > "
            f"must_start_by={attempt.must_start_by}")

    # 10. determine LaunchAttempt identity (deterministic from route, stable
    #     for exact replay of an already-durable attempt -- mirrors the
    #     f"res-{route.route_id}" reservation identity convention)
    launch_attempt_id = f"latch-{route.route_id}"

    # 11. derive canonical EA-4D.3 idempotency key (requires reservation_hash
    #     from the durable reservation + route lineage; computed BEFORE the
    #     attempt so there is no circular dependency on artifact_hash)
    idempotency_key = _canonical_idempotency_key(
        launch_attempt_id=launch_attempt_id,
        reservation_id=reservation.reservation_id,
        reservation_hash=reservation.artifact_hash,
        route_id=route.route_id,
        route_hash=route.artifact_hash,
    )

    # 12. build immutable ExecutionLaunchAttempt.
    #     Binding provenance from the RESOLVED binding, NOT the registry's copy.
    #     (EA-4D.2.2 candidate_binding_* from "resolution evidence"; EA-4D.3
    #     section 14 runtime_binding_id/version/hash from resolved binding.)
    attempt = build_execution_launch_attempt(
        launch_attempt_id=launch_attempt_id,
        reservation_id=reservation.reservation_id,
        reservation_hash=reservation.artifact_hash,
        route_id=route.route_id,
        route_hash=route.artifact_hash,
        attempt_id=attempt.attempt_id,
        attempt_hash=attempt.artifact_hash,
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        task_id=attempt.task_id,
        worker_id=binding.worker_id,
        worker_class=binding.worker_class,
        worker_version=binding.worker_version,
        operation=attempt.operation,
        input_hash=attempt.input_hash,
        runtime_binding_id=binding.runtime_binding_id,
        runtime_binding_version=binding.runtime_binding_version,
        runtime_binding_hash=binding.artifact_hash,
        idempotency_key=idempotency_key,
        recorded_at=now,
        must_start_by=attempt.must_start_by,
        launcher_actor=launcher_actor,
        status=ExecutionLaunchAttemptStatus.RECORDED,
    )

    # 13-15. persist launch attempt + LAUNCH_ATTEMPT_RECORDED, COMMIT
    return start_store.record_launch_attempt(attempt=attempt, now=now)
