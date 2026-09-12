"""EA-4D.2 execution-start service: exclusive start admission (stops at START_RESERVED).

This service is the orchestration boundary for EA-4D.2. It loads the
authoritative persisted ``WorkerRouteDecision`` (ROUTE_SELECTED, owned by the
EA-4C execution-authority store), gathers the complete immutable lineage,
builds an ``ExecutionStartReservation`` domain artifact, and durably admits it
exactly once via ``SQLiteExecutionStartStore.reserve_start``.

The service STOPS at START_RESERVED. It never:
* persists or orchestrates an ExecutionLaunchAttempt;
* invokes a worker, subprocess, or network call;
* transitions to EXECUTING.

That is EA-4D.3.

Concurrency model mirrors EA-4C.4: concurrent start coordinators each use their
OWN ``SQLiteExecutionStartStore`` instance pointed at the SAME db file; the
store owns mutual exclusion via BEGIN IMMEDIATE + UNIQUE(route_id). Replay and
lost-INSERT conflict normalization live in the store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from tools.hermes_core.execution_authorization import (
    ExecutionAttemptStatus,
)
from tools.hermes_core.execution_authorization_store import (
    ExecutionAuthorizationStoreError,
)
from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionStartConflictError,
    ExecutionStartIntegrityError,
    ExecutionStartLineageError,
    ExecutionStartReservation,
    ExecutionStartReservationStatus,
    build_execution_start_reservation,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import (
    ExecutionStartExpiredError,
    ExecutionStartStoreError,
    SQLiteExecutionStartStore,
)
from tools.hermes_core.worker_router import (
    WorkerRegistry,
    WorkerRouteDecision,
    WorkerRouteStatus,
)


class ExecutionStartServiceError(Exception):
    """Service-layer error for EA-4D.2 start admission."""


def reserve_execution_start(
    *,
    store: SQLiteExecutionAuthorizationStore,
    start_store: SQLiteExecutionStartStore,
    attempt_id: str,
    launcher_actor: ExecutionLauncherActor,
    worker_registry: Optional[WorkerRegistry] = None,
    clock: Optional[object] = None,
) -> ExecutionStartReservation:
    """Admon exactly one START_RESERVED reservation derived from THREE independently
    verified durable facts:

        1. a verified WorkerRouteDecision (ROUTE_SELECTED)
        2. a verified ExecutionAttempt (from the Authority store read API)
        3. a verified ExecutionAuthorization (from the Authority store read API)

    The reservation's lineage hashes are bound to the DURABLE Attempt and
    Authorization artifacts -- never to the Route's copied downstream fields.
    The Route is used only as evidence to COMPARE against the durable Attempt;
    it is not the authoritative source for attempt/authorization identity.

    The service STOPS at START_RESERVED. It never persists/launches an
    ExecutionLaunchAttempt, invokes a worker, or transitions to EXECUTING.
    """
    if not attempt_id:
        raise ExecutionStartServiceError("attempt_id is required")
    if launcher_actor.actor_type.value != "SYSTEM_LAUNCHER":
        raise ExecutionStartServiceError(
            "only SYSTEM_LAUNCHER may reserve execution start")

    # --- load + verify Route (authoritative EA-4C read) --------------------
    try:
        route = store.get_route_for_attempt(attempt_id)
    except ExecutionAuthorizationStoreError as exc:
        raise ExecutionStartIntegrityError(
            f"could not load route for attempt {attempt_id}: {exc}") from exc

    if route is None:
        raise ExecutionStartLineageError(
            f"attempt {attempt_id} has no ROUTE_SELECTED; cannot reserve start")
    if not isinstance(route, WorkerRouteDecision):
        raise ExecutionStartIntegrityError("loaded object is not a WorkerRouteDecision")
    # The EA-4C route read API does not independently verify the route, so
    # EA-4D.2 must explicitly verify it and require SELECTED.
    if not route.verify_hash():
        raise ExecutionStartIntegrityError(
            f"route for attempt {attempt_id} failed hash verification; refusing")
    if route.status != WorkerRouteStatus.SELECTED:
        raise ExecutionStartIntegrityError(
            f"route for attempt {attempt_id} is not SELECTED "
            f"(status={route.status}); cannot reserve start")

    # --- load + verify Attempt (Authority store read API verifies hash) -----
    attempt = store.get_attempt(attempt_id)
    if attempt is None:
        raise ExecutionStartLineageError(
            f"attempt {attempt_id} not found in authority store")
    # get_attempt already verifies artifact hash + physical linkage on read.
    # Require the frozen admissible Attempt state at this boundary.
    if attempt.status != ExecutionAttemptStatus.RECORDED:
        raise ExecutionStartIntegrityError(
            f"attempt {attempt_id} is not RECORDED (status={attempt.status})")

    # --- load + verify Authorization (Authority store read API) ------------
    authorization = store.get_authorization(attempt.authorization_id)
    if authorization is None:
        raise ExecutionStartLineageError(
            f"authorization {attempt.authorization_id} not found")
    # get_authorization already verifies integrity on read.

    # --- route <-> attempt lineage (exact equality) ------------------------
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
    _require_equal("route.worker_class", route.worker_class, attempt.worker_class)

    # --- route <-> authorization lineage -----------------------------------
    _require_equal("route.authorization_id", route.authorization_id,
                   authorization.authorization_id)
    _require_equal("route.authorization_hash", route.authorization_hash,
                   authorization.artifact_hash)

    # --- attempt <-> authorization lineage --------------------------------
    _require_equal("attempt.authorization_id", attempt.authorization_id,
                   authorization.authorization_id)
    _require_equal("attempt.authorization_hash", attempt.authorization_hash,
                   authorization.artifact_hash)

    # --- deadline: authoritative from verified Attempt --------------------
    _require_equal("route.must_start_by", route.must_start_by, attempt.must_start_by)
    must_start_by = attempt.must_start_by

    # --- clock: captured exactly once, validated canonical UTC -------------
    now = _capture_clock(clock)

    # --- worker identity: owned by Route (already proven == Attempt) -------
    worker_id = route.worker_id
    worker_class = route.worker_class
    worker_version = _resolve_worker_version(route, worker_registry)

    # --- bind reservation from DURABLE artifacts, not Route copies ---------
    reservation = build_execution_start_reservation(
        reservation_id=f"res-{route.route_id}",
        route_id=route.route_id,
        route_hash=route.artifact_hash,
        attempt_id=attempt.attempt_id,
        attempt_hash=attempt.artifact_hash,
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        claim_id=attempt.claim_id,
        claim_hash=attempt.claim_hash,
        request_id=attempt.request_id,
        request_hash=attempt.request_hash,
        decision_id=attempt.decision_id,
        decision_hash=attempt.decision_hash,
        task_id=attempt.task_id,
        worker_id=worker_id,
        worker_class=worker_class,
        worker_version=worker_version,
        operation=attempt.operation,
        input_hash=attempt.input_hash,
        reserved_at=now,
        must_start_by=must_start_by,
        launcher_actor=launcher_actor,
        status=ExecutionStartReservationStatus.RESERVED,
    )

    try:
        return start_store.reserve_start(reservation, now=now, must_start_by=must_start_by)
    except ExecutionStartExpiredError:
        raise
    except ExecutionStartConflictError:
        raise
    except ExecutionStartStoreError:
        raise


def _require_equal(label, a, b):
    if a != b:
        raise ExecutionStartLineageError(
            f"EA-4D.2 lineage mismatch: {label}: route/attempt/authorization "
            f"value differs ({a!r} != {b!r})")


def _resolve_worker_version(
    route: WorkerRouteDecision,
    worker_registry: Optional[WorkerRegistry],
) -> str:
    """Resolve exact worker version from the route-bound registry when supplied."""
    if worker_registry is None:
        return "1"
    if not worker_registry.verify_hash():
        raise ExecutionStartIntegrityError(
            "worker registry failed hash verification")
    _require_equal(
        "worker_registry_version",
        route.worker_registry_version,
        worker_registry.registry_version,
    )
    _require_equal(
        "worker_registry_hash",
        route.worker_registry_hash,
        worker_registry.registry_hash,
    )
    matches = [
        worker for worker in worker_registry.workers
        if worker.worker_id == route.worker_id
        and worker.worker_class == route.worker_class
    ]
    if len(matches) != 1:
        raise ExecutionStartLineageError(
            "selected worker does not resolve uniquely in verified registry")
    worker = matches[0]
    if not worker.verify_hash() or not worker.enabled:
        raise ExecutionStartIntegrityError(
            "selected worker descriptor is invalid or disabled")
    return worker.worker_version


def _capture_clock(clock):
    """Capture the clock exactly once and validate a canonical UTC 'Z' form."""
    from tools.hermes_core.worker_router_service import utc_now

    if clock is None:
        value = utc_now()
    else:
        value = clock()
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ExecutionStartIntegrityError(
            f"start clock must yield an absolute UTC timestamp ending in 'Z', "
            f"got {value!r}")
    # Validate parseability as canonical UTC.
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except Exception as exc:  # noqa: BLE001 - fail closed on malformed clock
        raise ExecutionStartIntegrityError(
            f"start clock is not a parseable canonical UTC timestamp: {exc}") from exc
    return value
