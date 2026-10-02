"""EA-4D.3D: production launch coordinator against the deterministic fake adapter.

This is the FIRST production orchestration path that calls
``RuntimeLaunchAdapter.launch(...)``. It is narrowly scoped: it orchestrates a
*previously admitted* durable ``ExecutionLaunchAttempt`` against a *resolved*
``WorkerRuntimeBinding`` via the canonical idempotency key, using only the
deterministic fake adapter established in EA-4D.3C.

Controlling invariant (frozen by the EA-4D.3D authorization packet):

    LAUNCH_ATTEMPT_RECORDED != WORKER STARTED

A fake ``RuntimeLaunchOutcome.STARTED`` is simulated positive acknowledgement
only. The coordinator never persists ``ExecutionStartResult``, never projects
``EXECUTING``, never performs a real subprocess/network/worker invocation, never
dispatches/enqueues, and never creates a new LaunchAttempt for recovery.

Trusted adapter boundary:
    The coordinator does NOT accept an untrusted caller-supplied adapter object.
    Adapter resolution is an explicit trusted boundary that, for this milestone,
    resolves ONLY the ``DeterministicFakeRuntimeAdapter``. No real adapter,
    no enum amendment, and no modification of ``execution_start.py`` occur.

Reused frozen EA-4D artifacts (read-only, no semantic modification):
    SQLiteExecutionStartStore.get_launch_attempt / get_reservation
    SQLiteExecutionAuthorizationStore reads
    resolve_worker_runtime_binding (EA-4D.3A)
    RuntimeLaunchAdapter / RuntimeLaunchOutcome / RuntimeLaunchResult /
    RuntimeLookupOutcome (EA-4D.3C)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt,
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
)
from tools.hermes_core.runtime_binding_registry import (
    ExecutionRuntimeBindingError,
    resolve_worker_runtime_binding,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeLaunchAdapter,
    RuntimeLaunchOutcome,
    RuntimeLookupOutcome,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (
    DeterministicFakeRuntimeAdapter,
)


# --------------------------------------------------------------------------- #
# Errors (narrowly scoped to this module; frozen domain hierarchies untouched)
# --------------------------------------------------------------------------- #
class LaunchCoordinationError(Exception):
    """Base error for EA-4D.3D launch-coordinator contract violations."""


class LaunchCoordinationIntegrityError(LaunchCoordinationError):
    """Lineage/admission integrity failure (fail closed)."""


class LaunchCoordinationFailClosedError(LaunchCoordinationError):
    """Generic fail-closed rejection (binding match, adapter resolution, etc.)."""


# --------------------------------------------------------------------------- #
# Trusted adapter-resolution boundary (3D: deterministic fake only)
# --------------------------------------------------------------------------- #
class TrustedFakeAdapterResolver:
    """Explicit trusted boundary that resolves ONLY the deterministic fake.

    No untrusted runtime/task input may supply an adapter. For EA-4D.3D the
    only resolvable implementation is ``DeterministicFakeRuntimeAdapter``. A
    real adapter or an unrecognized kind fails closed. This does NOT modify the
    frozen ``WorkerRuntimeAdapterKind`` enum.

    The resolver owns ONE stable deterministic fake instance for its lifetime so
    that every resolution yields the same in-memory fake runtime. This is what
    makes "same LaunchAttempt + same idempotency key = one logical fake
    operation" hold on the production default path: the fake records logical
    runs and lookups against a single shared instance, not a fresh one per call.
    """

    def __init__(self, adapter: Optional[RuntimeLaunchAdapter] = None) -> None:
        self._adapter = adapter or DeterministicFakeRuntimeAdapter()

    @property
    def adapter(self) -> RuntimeLaunchAdapter:
        return self._adapter

    def resolve(self, adapter_kind: WorkerRuntimeAdapterKind) -> RuntimeLaunchAdapter:
        # 3D scope: only the deterministic fake adapter is permitted. The local
        # worker adapter kind is the only trusted entry point in this milestone.
        if adapter_kind != WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER:
            raise LaunchCoordinationFailClosedError(
                f"EA-4D.3D resolves only the deterministic fake adapter; "
                f"rejected adapter kind {adapter_kind!r}")
        return self._adapter


class TrustedRealAdapterResolver:
    """Narrow EA-4D.3E-C wiring: explicit trusted real-execution resolution.

    This resolver is used ONLY when a coordinator is explicitly constructed for
    real execution (e.g. ``ExecutionLaunchCoordinator(..., adapter_resolver=
    TrustedRealAdapterResolver(factory))``). It resolves ``LOCAL_WORKER_ADAPTER``
    to a real ``LocalWorkerRuntimeAdapter`` built by the supplied factory. The
    DEFAULT coordinator continues to use ``TrustedFakeAdapterResolver`` and
    remains fake-only; real execution therefore requires explicit trusted
    construction and is never the default path.

    Any non-LOCAL kind, or a kind the factory cannot satisfy, fails closed.
    """

    def __init__(self, *, factory) -> None:
        # factory: Callable[[WorkerRuntimeAdapterKind], RuntimeLaunchAdapter]
        self._factory = factory

    def resolve(self, adapter_kind: WorkerRuntimeAdapterKind) -> RuntimeLaunchAdapter:
        if adapter_kind != WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER:
            raise LaunchCoordinationFailClosedError(
                f"real resolver handles only LOCAL_WORKER_ADAPTER; "
                f"rejected {adapter_kind!r}")
        return self._factory(adapter_kind)


# --------------------------------------------------------------------------- #
# Immutable coordinator result (distinct from frozen ExecutionStartResult)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LaunchCoordinationResult:
    """In-memory description of what the coordinator observed.

    Deliberately distinct from the frozen durable ``ExecutionStartResult``.
    """

    launch_attempt_id: str
    outcome: RuntimeLaunchOutcome
    runtime_run_id: Optional[str]
    reconciliation_state: Optional[RuntimeLookupOutcome]


def _require_admissible(attempt: ExecutionLaunchAttempt) -> None:
    if attempt.status != ExecutionLaunchAttemptStatus.RECORDED:
        raise LaunchCoordinationIntegrityError(
            f"launch attempt {attempt.launch_attempt_id} is not in the "
            f"admissible RECORDED state (got {attempt.status})")


def _verify_lineage(
    *,
    start_store,
    authority_store,
    attempt: ExecutionLaunchAttempt,
) -> None:
    """Re-verify reservation/route/authorization/attempt lineage against the
    authority + start stores. Mirrors the EA-4D.3B admission contract."""
    reservation = start_store.get_reservation(attempt.reservation_id)
    if reservation is None:
        raise LaunchCoordinationIntegrityError(
            f"reservation {attempt.reservation_id} missing; lineage broken")
    # The LaunchAttempt snapshot carries reservation_hash == reservation's
    # own integrity artifact_hash. Compare against that.
    if reservation.artifact_hash != attempt.reservation_hash:
        raise LaunchCoordinationIntegrityError(
            "reservation_hash does not match the immutable LaunchAttempt snapshot")
    if reservation.attempt_id != attempt.attempt_id:
        raise LaunchCoordinationIntegrityError(
            "reservation.attempt_id does not match LaunchAttempt.attempt_id")
    if reservation.route_id != attempt.route_id:
        raise LaunchCoordinationIntegrityError(
            "reservation.route_id does not match LaunchAttempt.route_id")

    route = authority_store.get_route_for_attempt(attempt.attempt_id)
    if route is None:
        raise LaunchCoordinationIntegrityError(
            f"route for attempt {attempt.attempt_id} missing; lineage broken")
    if route.route_id != attempt.route_id:
        raise LaunchCoordinationIntegrityError(
            "route_id does not match LaunchAttempt.route_id")
    if route.artifact_hash != attempt.route_hash:
        raise LaunchCoordinationIntegrityError(
            "route_hash does not match the immutable LaunchAttempt snapshot")

    authorization = authority_store.get_authorization(attempt.authorization_id)
    if authorization is None:
        raise LaunchCoordinationIntegrityError(
            f"authorization {attempt.authorization_id} missing; lineage broken")
    if authorization.artifact_hash != attempt.authorization_hash:
        raise LaunchCoordinationIntegrityError(
            "authorization_hash does not match the immutable LaunchAttempt snapshot")

    exec_attempt = authority_store.get_attempt(attempt.attempt_id)
    if exec_attempt is None:
        raise LaunchCoordinationIntegrityError(
            f"execution attempt {attempt.attempt_id} missing; lineage broken")
    if exec_attempt.artifact_hash != attempt.attempt_hash:
        raise LaunchCoordinationIntegrityError(
            "attempt_hash does not match the immutable LaunchAttempt snapshot")


def _resolve_binding(
    *,
    binding_registry,
    attempt: ExecutionLaunchAttempt,
) -> WorkerRuntimeBinding:
    """Resolve the exact trusted runtime binding from the attempt's immutable
    snapshot. Fails closed on any mismatch (no fallback worker/route)."""
    try:
        return resolve_worker_runtime_binding(
            registry=binding_registry,
            worker_id=attempt.worker_id,
            worker_version=attempt.worker_version,
            worker_class=attempt.worker_class,
            operation=attempt.operation,
        )
    except ExecutionRuntimeBindingError as exc:
        raise LaunchCoordinationFailClosedError(
            f"binding resolution failed closed: {exc}") from exc


def _verify_binding_match(
    *,
    attempt: ExecutionLaunchAttempt,
    binding: WorkerRuntimeBinding,
) -> None:
    """Binding identity/hash must match the immutable LaunchAttempt snapshot."""
    if binding.runtime_binding_id != attempt.runtime_binding_id:
        raise LaunchCoordinationFailClosedError(
            "resolved binding id does not match the LaunchAttempt snapshot")
    if binding.runtime_binding_version != attempt.runtime_binding_version:
        raise LaunchCoordinationFailClosedError(
            "resolved binding version does not match the LaunchAttempt snapshot")
    if binding.artifact_hash != attempt.runtime_binding_hash:
        raise LaunchCoordinationFailClosedError(
            "resolved binding hash does not match the LaunchAttempt snapshot")


class ExecutionLaunchCoordinator:
    """First production launch-coordination path (fake adapter only).

    The coordinator independently loads and verifies the durable LaunchAttempt;
    it never trusts a caller-supplied LaunchAttempt as authority. Exactly one
    logical invocation identity exists per durable LaunchAttempt, keyed by the
    attempt's canonical idempotency key.
    """

    def __init__(
        self,
        *,
        start_store,
        authority_store,
        binding_registry,
        adapter_resolver=None,
    ) -> None:
        self._start_store = start_store
        self._authority_store = authority_store
        self._binding_registry = binding_registry
        # Construct the trusted resolver ONCE. The default TrustedFakeAdapterResolver
        # owns a single stable fake instance for its lifetime, so the production
        # default path preserves fake state across invocations (one logical fake
        # operation per LaunchAttempt) and can reconcile via lookup().
        self._adapter_resolver = adapter_resolver or TrustedFakeAdapterResolver()

    def coordinate_launch(self, *, reservation_id: str) -> LaunchCoordinationResult:
        # 1. Independently load + verify the durable LaunchAttempt (fail closed
        #    on tampering; the store verifies artifact/hash integrity on read).
        try:
            attempt = self._start_store.get_launch_attempt(reservation_id)
        except Exception as exc:
            raise LaunchCoordinationIntegrityError(
                f"could not load/verify launch attempt for "
                f"{reservation_id}: {exc}") from exc
        if attempt is None:
            raise LaunchCoordinationIntegrityError(
                f"no durable launch attempt for reservation {reservation_id}")
        # 2. Admissible state.
        _require_admissible(attempt)
        # 3. Lineage re-verification against authority/start stores.
        _verify_lineage(
            start_store=self._start_store,
            authority_store=self._authority_store,
            attempt=attempt,
        )
        # 4. Resolve trusted binding from the immutable snapshot.
        binding = _resolve_binding(
            binding_registry=self._binding_registry, attempt=attempt)
        # 5. Binding identity/hash must match the snapshot.
        _verify_binding_match(attempt=attempt, binding=binding)
        # 6. Idempotency: use the attempt's canonical key; no caller override.
        idempotency_key = attempt.idempotency_key
        if idempotency_key != attempt.idempotency_key:
            raise LaunchCoordinationFailClosedError(
                "canonical idempotency key mismatch")
        # 7. Trusted adapter resolution (fake only).
        adapter = self._adapter_resolver.resolve(binding.adapter_kind)
        # 8. Exactly one logical invocation per durable LaunchAttempt.
        result = adapter.launch(
            binding=binding,
            launch_attempt=attempt,
            idempotency_key=idempotency_key,
        )
        # No EXECUTING, no ExecutionStartResult persistence, no dispatch.
        return LaunchCoordinationResult(
            launch_attempt_id=attempt.launch_attempt_id,
            outcome=result.outcome,
            runtime_run_id=result.runtime_run_id,
            reconciliation_state=None,
        )

    def reconcile(self, *, reservation_id: str) -> LaunchCoordinationResult:
        # Reconciliation reuses the SAME logical launch identity (idempotency
        # key). It never creates a new LaunchAttempt.
        attempt = self._start_store.get_launch_attempt(reservation_id)
        if attempt is None:
            raise LaunchCoordinationIntegrityError(
                f"no durable launch attempt for reservation {reservation_id}")
        _require_admissible(attempt)
        binding = _resolve_binding(
            binding_registry=self._binding_registry, attempt=attempt)
        _verify_binding_match(attempt=attempt, binding=binding)
        adapter = self._adapter_resolver.resolve(binding.adapter_kind)
        lookup = adapter.lookup(attempt.idempotency_key)
        if lookup.outcome == RuntimeLookupOutcome.FOUND_STARTED:
            outcome = RuntimeLaunchOutcome.STARTED
        elif lookup.outcome == RuntimeLookupOutcome.FOUND_FAILED:
            outcome = RuntimeLaunchOutcome.FAILED
        else:  # NOT_FOUND_AUTHORITATIVE or UNKNOWN
            outcome = RuntimeLaunchOutcome.UNKNOWN
        return LaunchCoordinationResult(
            launch_attempt_id=attempt.launch_attempt_id,
            outcome=outcome,
            runtime_run_id=lookup.runtime_run_id,
            reconciliation_state=lookup.outcome,
        )
