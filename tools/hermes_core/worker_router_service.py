"""EA-4C.3: WorkerRouter deterministic eligibility, selection, and start-window admission (SELECTION ONLY).

This module is the pre-execution routing service. It may:

* load + verify one durable ``ExecutionAttempt`` from the store;
* validate the current-time start window (``now <= attempt.must_start_by``);
* load + verify the persisted ``ExecutionAuthorization`` scope;
* validate the supplied immutable ``WorkerRegistry`` snapshot;
* filter eligible workers against the persisted scope + registry;
* deterministically select exactly one worker (stable sort, no randomness);
* construct a ``WorkerRouteDecision`` via the EA-4C.1 builder;
* persist that route through the EA-4C.2 ``record_route(...)`` layer;
* return the ``ROUTE_SELECTED`` decision and STOP.

It must NOT launch, dispatch, enqueue, invoke, or execute the selected worker.
It does NOT define actual worker launch timing. It ends at ``ROUTE_SELECTED``.

Frozen state separation (governing invariants):

    ACCEPTED
    != AUTHORIZED
    != CLAIMED
    != EXECUTION_ATTEMPT_RECORDED
    != ROUTE_SELECTED
    != EXECUTING

Absolute invariant:

    ACCEPTED != EXECUTION AUTHORIZATION

SYSTEM_ROUTER (WorkerRouterActorType.SYSTEM_ROUTER) is a bounded routing-only
identity. It may produce a route decision; it grants no execution authority and
may not launch/dispatch anything.

Concurrency boundary (EA-4C.3 vs EA-4C.4):
    This module handles the case where a route ALREADY EXISTS before persistence
    (the pre-existing-route replay/conflict fast path). It does NOT handle a
    lost ``record_route`` INSERT race: that post-failure re-read normalization
    is the EA-4C.4 concurrency proof and is intentionally absent here. The
    terminal persistence path wraps ``store.record_route`` failures only in
    ``ExecutionAuthorizationStoreError`` (store -> routing-domain translation);
    it never re-reads the store after a failed INSERT, and it never special-cases
    ``ExecutionAuthorizationConflictError``.

Design source of truth:
    docs/architecture/HERMES_EA4C_WORKER_ROUTER_DESIGN_AUTHORIZATION.md
    Downloads/HERMES_EA4C3_DETERMINISTIC_WORKER_SELECTION_AUTHORIZATION.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .execution_authorization import (
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionAuthorization,
    ExecutionAuthorizationScope,
)
from .worker_router import (
    WorkerRegistryIntegrityError,
    WorkerRouteConflictError,
    WorkerRouteError,
    WorkerRouteExpiredError,
    WorkerRouteIntegrityError,
    WorkerRouteLineageError,
    WorkerRouteNoEligibleWorkerError,
    WorkerRouteNotFoundError,
    WorkerRouterActor,
    WorkerRoutingPolicyRef,
    WorkerRouteDecision,
    WorkerRegistry,
    build_worker_route_decision,
)

# Imported only for exception translation (so raw store/SQLite errors never
# leak out of the routing service -- EA-4C.3). NOTE: ExecutionAuthorizationStoreError
# is the ONLY store exception imported here. The EA-4C.4 lost-INSERT-race
# special-case (ExecutionAuthorizationConflictError + post-failure reread) is NOT
# present in EA-4C.3.
from .sqlite_execution_authorization_store import (
    ExecutionAuthorizationStoreError,
    SQLiteExecutionAuthorizationStore,
)


# --------------------------------------------------------------------------- #
# Clock
# --------------------------------------------------------------------------- #

#: A clock returns a canonical absolute UTC timestamp ending in ``Z``
#: (``YYYY-MM-DDTHH:MM:SSZ``), consistent with existing EA time semantics.
Clock = Callable[[], str]


def utc_now() -> str:
    """Default injectable clock: canonical absolute UTC timestamp (Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_z(value: str) -> datetime:
    """Parse an absolute UTC ``Z`` timestamp into a tz-aware datetime.

    Fail-closed: a non-string, non-``Z``, or unparseable value raises
    ``WorkerRouteError`` (covers clock failure / invalid / non-UTC time).
    """
    if not isinstance(value, str):
        raise WorkerRouteError(f"timestamp must be a string, got {type(value).__name__}")
    if not value.endswith("Z"):
        raise WorkerRouteError(
            f"timestamp must be absolute UTC ending in 'Z' (RFC3339/ISO-8601), got {value!r}"
        )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise WorkerRouteError(f"invalid UTC timestamp: {value!r}") from exc


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _verify_registry(registry: WorkerRegistry) -> None:
    """Fail closed on tampered registry or duplicate worker ids."""
    if not isinstance(registry, WorkerRegistry):
        raise WorkerRouteError("registry must be a WorkerRegistry")
    if not registry.verify_hash():
        raise WorkerRegistryIntegrityError("worker registry failed hash verification")
    seen: set[str] = set()
    for worker in registry.workers:
        if worker.worker_id in seen:
            raise WorkerRegistryIntegrityError(
                f"duplicate worker_id in registry: {worker.worker_id}"
            )
        seen.add(worker.worker_id)


def _eligible_workers(
    *,
    attempt: ExecutionAttempt,
    scope: ExecutionAuthorizationScope,
    registry: WorkerRegistry,
) -> list[Any]:
    """Return the eligible workers under the frozen EA-4C.3 policy.

    A candidate is eligible only if ALL required predicates pass:

        worker.enabled == True
        worker.worker_class == attempt.worker_class == scope.worker_class
        attempt.operation in worker.allowed_operations

    Scope equality (worker_class / operation / input_hash) is enforced by the
    caller before this filter runs. Capabilities, if present, may only narrow
    eligibility and never broaden authority, so they are intentionally NOT a
    broadening predicate here.
    """
    eligible: list[Any] = []
    for worker in registry.workers:
        if not worker.enabled:
            continue
        if worker.worker_class != attempt.worker_class:
            continue
        if worker.worker_class != scope.worker_class:
            continue
        if attempt.operation not in worker.allowed_operations:
            continue
        eligible.append(worker)
    return eligible


def _select_deterministic(workers: list[Any]) -> Any:
    """Stable deterministic selection: sort by (class, id, version), take first.

    No randomness, no filesystem/pid/port/wall-clock tie-break, no load or
    latency heuristic, no dependence on registry insertion order.
    """
    ordered = sorted(
        workers,
        key=lambda w: (w.worker_class or "", w.worker_id, w.worker_version),
    )
    return ordered[0]


def _attempt_lineage_error(store_err: ExecutionAuthorizationStoreError) -> WorkerRouteError:
    """Translate a store-level error into a routing-domain error (no leak)."""
    return WorkerRouteError(f"store error during routing: {store_err}")


def _resolve_existing_route(
    *,
    store: SQLiteExecutionAuthorizationStore,
    existing: WorkerRouteDecision,
    attempt_id: str,
    registry: WorkerRegistry,
    policy: WorkerRoutingPolicyRef,
    router_actor: WorkerRouterActor,
) -> WorkerRouteDecision:
    """Resolve the replay/conflict semantics of an ALREADY-DURABLE route.

    This helper is reachable ONLY from the pre-routing fast path (the caller
    checks for an already-durable route before selecting). It is NEVER reached
    from a failed ``record_route`` INSERT. The EA-4C.4 lost-INSERT-race reread
    normalization deliberately does not exist in this module (see concurrency
    boundary note at file top).

    Terminal semantics (EA-4C.3):

    * re-derive what the CURRENT context WOULD select and confirm the
      replay-significant inputs (selected worker, routing policy identity,
      router-actor identity) all agree with the persisted route;
    * if all agree -> exact replay: return the existing route (no new row/event);
    * otherwise -> ``WorkerRouteConflictError``; existing route stays authoritative
      and is never silently rerouted or inherited under a changed context.
    """
    attempt, scope = _load_attempt_and_scope(store, attempt_id)
    _verify_registry(registry)

    policy_ok = (
        existing.routing_policy_id == policy.policy_id
        and existing.routing_policy_version == policy.policy_version
        and existing.routing_policy_hash == policy.policy_hash
    )
    actor_ok = (
        existing.router_actor_id == router_actor.actor_id
        and existing.router_actor_type == router_actor.actor_type.value
        and existing.router_actor_context == router_actor.actor_context
    )
    candidate = _eligible_workers(attempt=attempt, scope=scope, registry=registry)
    if not candidate:
        # No eligible worker under current registry: the original route's
        # worker may no longer be present. Existing route remains authoritative;
        # this is a conflict (cannot re-validate), not a silent reroute.
        raise WorkerRouteConflictError(
            "attempt already has a durable route but the current registry "
            "yields no eligible worker; existing route remains authoritative"
        )
    selected = _select_deterministic(candidate)

    if selected.worker_id == existing.worker_id and policy_ok and actor_ok:
        return existing
    raise WorkerRouteConflictError(
        "attempt already has a durable route that conflicts with the current "
        "routing context (worker/policy/actor); existing route remains "
        "authoritative"
    )


# --------------------------------------------------------------------------- #
# Public selection service
# --------------------------------------------------------------------------- #


def select_and_record_worker_route(
    *,
    store: SQLiteExecutionAuthorizationStore,
    attempt_id: str,
    registry: WorkerRegistry,
    policy: WorkerRoutingPolicyRef,
    router_actor: WorkerRouterActor,
    clock: Optional[Clock] = None,
) -> WorkerRouteDecision:
    """Deterministically select + persist exactly one worker route for an Attempt.

    The router loads the authoritative persisted Attempt from the store rather
    than trusting any caller-supplied Attempt object. Selection ends at
    ``ROUTE_SELECTED``; no worker is launched or dispatched.

    Returns the persisted ``WorkerRouteDecision``. On any unrecoverable routing
    condition raises a ``WorkerRouteError`` subclass (never a raw store/SQLite
    exception).

    Concurrency note: this EA-4C.3 path assumes the route does not already exist
    (the fast path above handles that) and that the single ``record_route`` call
    succeeds. A lost INSERT race is an EA-4C.4 concern and is intentionally NOT
    handled here.
    """
    if clock is None:
        clock = utc_now()
    if not attempt_id:
        raise WorkerRouteError("attempt_id is required")

    # --- replay: an existing route is authoritative -------------------------
    try:
        existing = store.get_route_for_attempt(attempt_id)
    except ExecutionAuthorizationStoreError as exc:
        raise _attempt_lineage_error(exc) from exc

    if existing is not None:
        # An existing durable route is already authoritative before we route.
        # This helper is reached ONLY from here (never from a failed INSERT).
        return _resolve_existing_route(
            store=store, existing=existing, attempt_id=attempt_id,
            registry=registry, policy=policy, router_actor=router_actor,
        )

    # --- load + verify durable Attempt --------------------------------------
    attempt, scope = _load_attempt_and_scope(store, attempt_id)

    # --- start-window admission (inclusive now <= must_start_by) ------------
    now = clock()
    now_dt = _parse_utc_z(now)  # also validates clock output
    must_start_dt = _parse_utc_z(attempt.must_start_by)
    if now_dt > must_start_dt:
        raise WorkerRouteExpiredError(
            f"route admission expired: now={now} > must_start_by={attempt.must_start_by}"
        )

    # --- registry validation ------------------------------------------------
    _verify_registry(registry)

    # --- eligibility + deterministic selection ------------------------------
    eligible = _eligible_workers(attempt=attempt, scope=scope, registry=registry)
    if not eligible:
        raise WorkerRouteNoEligibleWorkerError(
            "zero registered workers satisfy the eligibility policy for attempt "
            f"{attempt_id}"
        )
    selected = _select_deterministic(eligible)

    # --- build + persist route through EA-4C.2 ------------------------------
    route = build_worker_route_decision(
        attempt_id=attempt.attempt_id,
        attempt_hash=attempt.artifact_hash,
        authorization_id=attempt.authorization_id,
        authorization_hash=attempt.authorization_hash,
        claim_id=attempt.claim_id,
        claim_hash=attempt.claim_hash,
        request_id=attempt.request_id,
        request_hash=attempt.request_hash,
        decision_id=attempt.decision_id,
        decision_hash=attempt.decision_hash,
        task_id=attempt.task_id,
        worker_id=selected.worker_id,
        worker_class=selected.worker_class,
        registry=registry,
        policy=policy,
        selected_at=now,
        must_start_by=attempt.must_start_by,
        operation=attempt.operation,
        input_hash=attempt.input_hash,
        router_actor=router_actor,
    )
    try:
        store.record_route(route)
    except ExecutionAuthorizationStoreError as exc:
        # Normal EA-4C.3 store/domain translation only. No special-casing of
        # ExecutionAuthorizationConflictError; no post-failure reread.
        raise _attempt_lineage_error(exc) from exc
    return route


# --------------------------------------------------------------------------- #
# Shared loaders (fail closed)
# --------------------------------------------------------------------------- #


def _load_attempt_and_scope(
    store: SQLiteExecutionAuthorizationStore,
    attempt_id: str,
) -> tuple[ExecutionAttempt, ExecutionAuthorizationScope]:
    """Load the Attempt (missing/tampered/non-RECORDED fail closed) and its
    persisted Authorization scope (with scope-equality checks)."""
    try:
        attempt = store.get_attempt(attempt_id)
    except ExecutionAuthorizationStoreError as exc:
        # Load-time canonical-hash mismatch is an integrity failure.
        raise WorkerRouteIntegrityError(
            f"Attempt {attempt_id} failed integrity on load: {exc}"
        ) from exc
    if attempt is None:
        raise WorkerRouteNotFoundError(
            f"no persisted ExecutionAttempt for attempt_id={attempt_id!r}"
        )
    if not attempt.verify_hash():
        raise WorkerRouteIntegrityError(
            f"Attempt {attempt_id} failed hash verification"
        )
    if attempt.status != ExecutionAttemptStatus.RECORDED:
        raise WorkerRouteError(
            f"Attempt {attempt_id} must have status RECORDED to be routed, "
            f"got {attempt.status.value}"
        )

    try:
        auth = store.get_authorization(attempt.authorization_id)
    except ExecutionAuthorizationStoreError as exc:
        raise _attempt_lineage_error(exc) from exc
    if auth is None:
        raise WorkerRouteLineageError(
            f"no persisted Authorization {attempt.authorization_id!r} for attempt"
        )
    if not auth.verify_hash():
        raise WorkerRouteIntegrityError(
            f"Authorization {attempt.authorization_id} failed hash verification"
        )
    scope = auth.authorized_scope
    require_attempt_scope_matches_authorization(attempt, auth)
    return attempt, scope


def require_attempt_scope_matches_authorization(
    attempt: ExecutionAttempt,
    authorization: ExecutionAuthorization,
) -> None:
    """Fail closed if a valid Attempt's scope fields disagree with its durable
    Authorization scope.

    This is the EA-4C.3 Authorization-scope comparison. It is a pure
    comparison over cryptographically valid domain objects -- it does NOT touch
    the store or detect physical tampering (that is ``ExecutionAttempt.verify_hash``
    in the load path). The persisted Attempt is constructed so that its
    ``worker_class`` / ``operation`` / ``input_hash`` reflect the Authorization
    scope; a semantically inconsistent (but internally valid) Attempt would be
    caught here and rejected with ``WorkerRouteLineageError``.

    Equality required:

        attempt.worker_class == authorization.authorized_scope.worker_class
        attempt.operation    == authorization.authorized_scope.operation
        attempt.input_hash   == authorization.authorized_scope.input_hash
    """
    scope = authorization.authorized_scope
    if (
        attempt.worker_class != scope.worker_class
        or attempt.operation != scope.operation
        or attempt.input_hash != scope.input_hash
    ):
        raise WorkerRouteLineageError(
            "Attempt scope does not match persisted Authorization scope "
            "(worker_class / operation / input_hash)"
        )


def _registry_matches(route: WorkerRouteDecision, registry: WorkerRegistry) -> bool:
    """Whether the supplied registry snapshot matches the route's binding."""
    return (
        route.worker_registry_version == registry.registry_version
        and route.worker_registry_hash == registry.registry_hash
    )
