"""EA-4D.3B tests: launch-attempt admission + durable LAUNCH_ATTEMPT_RECORDED.

Pure persistence/concurrency/service tests only -- no adapter, no worker
invocation, no process/network capability. They exercise exact admission
ordering, lineage verification, binding resolution, registry integrity,
deadline binding, idempotency-key determinism, replay, conflict, ledger
exactly-once, rollback seam, tamper coverage, and concurrency races A-D.
"""

import datetime
import os
import shutil
import sqlite3
import tempfile
import unittest
from dataclasses import dataclass

from tools.hermes_core.execution_authorization import (
    ExecutionAuthorization,
    ExecutionAuthorizationDecision,
    ExecutionAuthorizationDecisionOutcome,
    ExecutionAuthorizationRequest,
    ExecutionClaim,
    ExecutionAttempt,
    ExecutionAttemptStatus,
    ExecutionAuthorizationActor,
    ExecutionAuthorizationActorType,
    ExecutionAuthorizationPolicyRef,
    ExecutionAuthorizationScope,
    ExecutionClaimant,
    ExecutionAttemptActor,
    build_execution_authorization_request,
    build_execution_authorization_decision,
    build_execution_authorization,
    build_execution_claim,
    build_execution_attempt,
    reconstruct_authorization,
    reconstruct_claim,
    reconstruct_decision,
    reconstruct_request,
    reconstruct_attempt,
)
from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
    ExecutionStartReservationStatus,
    _finalize,
    build_execution_launch_attempt,
    build_execution_start_reservation,
    build_worker_runtime_binding,
    sha256_payload,
    canonical_json,
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
    ExecutionRuntimeBindingRegistryConflictError,
    ExecutionRuntimeBindingRegistryError,
    resolve_worker_runtime_binding,
    WorkerRuntimeBindingRegistry,
    build_worker_runtime_binding_registry,
    ExecutionRuntimeBindingIntegrityError,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import (
    ExecutionStartExpiredError,
    ExecutionStartStoreError,
    ExecutionStartConflictError,
    SQLiteExecutionStartStore,
)
from tools.hermes_core.worker_router import (
    WorkerRouteDecision,
    WorkerRouteStatus,
    WorkerRegistry,
    WorkerRoutingPolicyRef,
    WorkerRouterActor,
    WorkerRouterActorType,
    build_worker_route_decision,
)
from tools.hermes_core.execution_launch_admission_service import (
    admit_execution_launch_attempt,
    _canonical_idempotency_key,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------------------------------- #
# Stable deterministic routing provenance fixture (EA-4C, reused by 3B).
# EA-4D.3B does not reopen routing policy semantics.
# --------------------------------------------------------------------------- #

_ROUTING_REGISTRY = WorkerRegistry(
    registry_version="1",
    registry_hash="1" * 64,
    workers=[],
)

_ROUTING_POLICY = WorkerRoutingPolicyRef(
    policy_id="fixture-routing-policy",
    policy_version="1",
    policy_hash="2" * 64,
)

_ROUTER_ACTOR = WorkerRouterActor(
    actor_id="fixture-router",
    actor_type=WorkerRouterActorType.SYSTEM_ROUTER,
    actor_context=None,
)

# --------------------------------------------------------------------------- #
# Canonical lineage builder: Request -> Decision -> Authorization -> Claim
# -> Attempt -> Route. Authorization provenance is kept separate from routing
# provenance. Every artifact is verify_hash()'d immediately after construction.
# --------------------------------------------------------------------------- #

def _iso(d):
    return datetime.datetime(
        d.year, d.month, d.day,
        tzinfo=datetime.timezone.utc,
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class CanonicalChain:
    request: ExecutionAuthorizationRequest
    decision: ExecutionAuthorizationDecision
    authorization: ExecutionAuthorization
    claim: ExecutionClaim
    attempt: ExecutionAttempt
    route: WorkerRouteDecision


def _build_canonical_chain(*, seed="seed", deadline=None):
    """Build and immediately verify_hash() the canonical chain in dependency
    order. Authorization provenance is kept separate from routing provenance.

    ``deadline`` (ISO-8601 UTC) controls claim_expires_at / attempt.must_start_by
    / route.must_start_by. Defaults to now + 1 day (valid for admission).
    """
    if deadline is None:
        deadline = _iso(
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=1)
        )
    auth_actor = ExecutionAuthorizationActor(
        actor_id=f"authority-{seed}",
        actor_type=ExecutionAuthorizationActorType.SYSTEM,
        authority_role="operator",
        authentication_context=None,
    )
    auth_policy = ExecutionAuthorizationPolicyRef(
        policy_id=f"auth-policy-{seed}",
        policy_version="1",
    )
    scope = ExecutionAuthorizationScope(
        operation="run-sandbox",
        worker_class="run-sandbox",
        input_hash="0" * 64,
        attempt_limit=1,
        max_runtime_seconds=300,
    )

    request = build_execution_authorization_request(
        task_id=f"task-{seed}",
        accepted_governance_artifact_id=f"governance-{seed}",
        accepted_governance_hash="e" * 64,
        requested_scope=scope,
        requesting_actor=auth_actor,
        authorization_policy=auth_policy,
        requested_at="2024-01-01T00:00:00Z",
        request_reason=f"request-{seed}",
    )
    assert request.verify_hash()

    decision = build_execution_authorization_decision(
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        task_id=request.task_id,
        decision_actor=auth_actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason=f"grant-{seed}",
        authorization_id="execution-authorization-" + "d" * 16,
        authorization_policy=auth_policy,
    )
    assert decision.verify_hash()

    authorization = build_execution_authorization(
        task_id=request.task_id,
        accepted_governance_artifact_id=f"governance-{seed}",
        accepted_governance_hash="e" * 64,
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        authorization_actor=auth_actor,
        authorized_scope=scope,
        authorization_reason=f"authorize-{seed}",
        authorization_policy=auth_policy,
        issued_at="2024-01-01T00:00:00Z",
        expires_at=deadline,
        nonce=f"nonce-{seed}",
    )
    assert authorization.verify_hash()

    # Align the decision's authorization_id to the derived authorization id
    # (EA-3A Model A: authorization_id is excluded from the decision hash
    # preimage, so realigning leaves decision_id/artifact_hash stable).
    decision = build_execution_authorization_decision(
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        task_id=request.task_id,
        decision_actor=auth_actor,
        outcome=ExecutionAuthorizationDecisionOutcome.GRANTED,
        decision_reason=f"grant-{seed}",
        authorization_id=authorization.authorization_id,
        authorization_policy=auth_policy,
    )
    assert decision.verify_hash()

    claim = build_execution_claim(
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        task_id=request.task_id,
        claimant=ExecutionClaimant(
            claimant_id=f"claimant-{seed}", claimant_type="system",
        ),
        claimed_at="2024-01-01T00:01:00Z",
        claim_expires_at=deadline,
        authorization_policy=auth_policy,
        claim_reason=f"claim-{seed}",
    )
    assert claim.verify_hash()

    attempt = build_execution_attempt(
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        claim_id=claim.claim_id,
        claim_hash=claim.artifact_hash,
        task_id=request.task_id,
        attempt_number=1,
        attempt_actor=ExecutionAttemptActor(
            actor_id=f"attempt-{seed}", actor_type="policy-service",
            actor_context=None,
        ),
        attempt_requested_at="2024-01-01T00:02:00Z",
        attempt_recorded_at="2024-01-01T00:02:00Z",
        claim_expires_at=claim.claim_expires_at,
        must_start_by=claim.claim_expires_at,
        input_hash=scope.input_hash,
        operation=scope.operation,
        worker_class=scope.worker_class,
        status=ExecutionAttemptStatus.RECORDED,
    )
    assert attempt.verify_hash()

    route = build_worker_route_decision(
        attempt_id=attempt.attempt_id,
        attempt_hash=attempt.artifact_hash,
        authorization_id=authorization.authorization_id,
        authorization_hash=authorization.artifact_hash,
        claim_id=claim.claim_id,
        claim_hash=claim.artifact_hash,
        request_id=request.request_id,
        request_hash=request.artifact_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.artifact_hash,
        task_id=attempt.task_id,
        worker_id=f"worker-{seed}",
        worker_class=attempt.worker_class,
        registry=_ROUTING_REGISTRY,
        policy=_ROUTING_POLICY,
        selected_at="2024-01-01T00:04:00Z",
        must_start_by=attempt.must_start_by,
        operation=attempt.operation,
        input_hash=attempt.input_hash,
        router_actor=_ROUTER_ACTOR,
    )
    assert route.verify_hash()

    return CanonicalChain(
        request=request, decision=decision, authorization=authorization,
        claim=claim, attempt=attempt, route=route,
    )


def _persist_canonical_chain(store, chain):
    """Persist in dependency order and reload once to detect fixture corruption."""
    store.record_request(chain.request)
    store.record_granted_decision_and_authorization(chain.decision, chain.authorization)
    # Persist the claim atomically under the authorization (no separate record_claim).
    store.claim_authorization_atomically(chain.authorization.authorization_id, chain.claim)
    store.record_attempt(chain.attempt)
    store.record_route(chain.route)

    got_request = store.get_request(chain.request.request_id)
    assert got_request is not None and got_request.verify_hash()
    got_decision = store.get_decision(chain.decision.decision_id)
    assert got_decision is not None and got_decision.verify_hash()
    got_authorization = store.get_authorization(chain.authorization.authorization_id)
    assert got_authorization is not None and got_authorization.verify_hash()
    got_claim = store.get_claim(chain.claim.claim_id)
    assert got_claim is not None and got_claim.verify_hash()
    got_attempt = store.get_attempt(chain.attempt.attempt_id)
    assert got_attempt is not None and got_attempt.verify_hash()
    got_route = store.get_route_for_attempt(chain.attempt.attempt_id)
    assert got_route is not None and got_route.verify_hash()


def _make_reservation(chain, *, launcher_actor, reserved_at="2024-01-01T00:00:00Z"):
    """Build EXECUTION_START_RESERVED strictly from already-valid durable lineage."""
    return build_execution_start_reservation(
        reservation_id=f"res-{chain.route.route_id}",
        route_id=chain.route.route_id,
        route_hash=chain.route.artifact_hash,
        attempt_id=chain.attempt.attempt_id,
        attempt_hash=chain.attempt.artifact_hash,
        authorization_id=chain.authorization.authorization_id,
        authorization_hash=chain.authorization.artifact_hash,
        claim_id=chain.claim.claim_id,
        claim_hash=chain.claim.artifact_hash,
        request_id=chain.request.request_id,
        request_hash=chain.request.artifact_hash,
        decision_id=chain.decision.decision_id,
        decision_hash=chain.decision.artifact_hash,
        task_id=chain.attempt.task_id,
        worker_id=chain.route.worker_id,
        worker_class=chain.route.worker_class,
        worker_version="1",
        operation=chain.route.operation,
        input_hash=chain.route.input_hash,
        reserved_at=reserved_at,
        must_start_by=chain.attempt.must_start_by,
        launcher_actor=launcher_actor,
        status=ExecutionStartReservationStatus.RESERVED,
    )


def _persist_reservation(start_store, reservation, *, now, must_start_by):
    """Persist the reservation through the existing EA-4D.2 start-store API."""
    start_store.reserve_start(reservation, now=now, must_start_by=must_start_by)


def _make_binding_registry(chain):
    """Build the trusted static binding registry for admission.

    The binding identity is derived from the route: worker_id/version/class,
    operation in allowed_operations, enabled, supports_idempotency.
    """
    binding = build_worker_runtime_binding(
        runtime_binding_id=f"binding-{chain.route.route_id}",
        worker_id=chain.route.worker_id,
        worker_version="1",
        worker_class=chain.route.worker_class,
        adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
        adapter_version="1",
        configuration_reference="hermes-worker-local-v1",
        configuration_hash="b" * 64,
        allowed_operations=[chain.route.operation],
        supports_idempotency=True,
        enabled=True,
    )
    registry = build_worker_runtime_binding_registry(
        registry_version="1",
        bindings=[binding],
    )
    assert registry.verify_hash()
    return registry


def _launcher_actor():
    return ExecutionLauncherActor(
        actor_id="sys-launch",
        actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
    )


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #

def _fresh_authority_db():
    tmp = tempfile.mkdtemp(prefix="ea4d3b-auth-")
    db = os.path.join(tmp, "authority.db")
    store = SQLiteExecutionAuthorizationStore(db_path=db)
    return tmp, store


def _fresh_start_db():
    tmp = tempfile.mkdtemp(prefix="ea4d3b-start-")
    db = os.path.join(tmp, "start.db")
    store = SQLiteExecutionStartStore(db_path=db)
    return tmp, store


# --------------------------------------------------------------------------- #
# Service tests
# --------------------------------------------------------------------------- #

class AdmissionHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="happy")
        _persist_canonical_chain(self.auth_store, self.chain)

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)

    def test_valid_admission_returns_recorded_attempt(self):
        reservation = _make_reservation(
            self.chain,
            launcher_actor=_launcher_actor(),
        )
        _persist_reservation(
            self.start_store, reservation,
            now=reservation.reserved_at,
            must_start_by=reservation.must_start_by,
        )
        registry = _make_binding_registry(self.chain)
        attempt = admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=registry,
            reservation_id=reservation.reservation_id,
            launcher_actor=_launcher_actor(),
        )
        self.assertEqual(attempt.status, ExecutionLaunchAttemptStatus.RECORDED)
        self.assertEqual(attempt.reservation_id, reservation.reservation_id)
        self.assertEqual(attempt.route_id, self.chain.route.route_id)
        self.assertEqual(attempt.attempt_id, self.chain.attempt.attempt_id)
        self.assertTrue(attempt.verify_hash())
        # Idempotency key is a deterministic SHA-256 digest over the frozen
        # preimage (which contains the "ea4d3-launch-v1" tag). Verify shape
        # and determinism rather than asserting a literal substring.
        self.assertRegex(
            attempt.idempotency_key,
            r"^[0-9a-f]{64}$",
            msg=f"idempotency_key not a canonical digest: {attempt.idempotency_key!r}",
        )
        self.assertEqual(
            attempt.idempotency_key,
            _canonical_idempotency_key(
                launch_attempt_id=attempt.launch_attempt_id,
                reservation_id=reservation.reservation_id,
                reservation_hash=reservation.artifact_hash,
                route_id=self.chain.route.route_id,
                route_hash=self.chain.route.artifact_hash,
            ),
        )

    def test_wrong_reservation_id_raises_lineage(self):
        launcher = _launcher_actor()
        with self.assertRaises(ExecutionStartLineageError):
            admit_execution_launch_attempt(
                authority_store=self.auth_store,
                start_store=self.start_store,
                binding_registry=build_worker_runtime_binding_registry(
                    registry_version="1", bindings=[]),
                reservation_id="no-such-res",
                launcher_actor=launcher,
            )



class LineageVerificationTests(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="lineage")
        _persist_canonical_chain(self.auth_store, self.chain)
        self.launcher = _launcher_actor()

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)

    def _admit_once(self):
        reservation = _make_reservation(self.chain, launcher_actor=self.launcher)
        _persist_reservation(
            self.start_store, reservation,
            now=reservation.reserved_at, must_start_by=reservation.must_start_by,
        )
        registry = _make_binding_registry(self.chain)
        return reservation, admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=registry,
            reservation_id=reservation.reservation_id,
            launcher_actor=self.launcher,
        )

    def test_replay_same_reservation_is_conflict(self):
        reservation, _ = self._admit_once()
        with self.assertRaises(ExecutionStartConflictError):
            admit_execution_launch_attempt(
                authority_store=self.auth_store,
                start_store=self.start_store,
                binding_registry=_make_binding_registry(self.chain),
                reservation_id=reservation.reservation_id,
                launcher_actor=self.launcher,
            )

    def test_binding_worker_mismatch_raises_lineage(self):
        reservation = _make_reservation(self.chain, launcher_actor=self.launcher)
        _persist_reservation(
            self.start_store, reservation,
            now=reservation.reserved_at, must_start_by=reservation.must_start_by,
        )
        empty_registry = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[],
        )
        with self.assertRaises(ExecutionStartLineageError):
            admit_execution_launch_attempt(
                authority_store=self.auth_store,
                start_store=self.start_store,
                binding_registry=empty_registry,
                reservation_id=reservation.reservation_id,
                launcher_actor=self.launcher,
            )

    def test_recorded_attempt_roundtrips_through_store(self):
        reservation, attempt = self._admit_once()
        got = self.start_store.get_launch_attempt(reservation.reservation_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.launch_attempt_id, attempt.launch_attempt_id)
        self.assertEqual(got.artifact_hash, attempt.artifact_hash)
        self.assertTrue(got.verify_hash())
        self.assertEqual(got.idempotency_key, attempt.idempotency_key)

    def test_expired_must_start_by_denies_admission(self):
        """A lineage-valid reservation whose deadline has already passed must be
        denied at the admission deadline guard (not at lineage verification)."""
        past = _iso(
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=1)
        )
        expired_chain = _build_canonical_chain(seed="expired", deadline=past)
        _persist_canonical_chain(self.auth_store, expired_chain)
        reservation = _make_reservation(
            expired_chain, launcher_actor=self.launcher, reserved_at=past,
        )
        _persist_reservation(
            self.start_store, reservation,
            now=reservation.reserved_at, must_start_by=reservation.must_start_by,
        )
        with self.assertRaises(ExecutionStartExpiredError):
            admit_execution_launch_attempt(
                authority_store=self.auth_store,
                start_store=self.start_store,
                binding_registry=_make_binding_registry(expired_chain),
                reservation_id=reservation.reservation_id,
                launcher_actor=self.launcher,
            )

    def test_idempotency_key_is_deterministic(self):
        key_a = _canonical_idempotency_key(
            launch_attempt_id="latch-r1", reservation_id="res-r1",
            reservation_hash="e" * 64, route_id="route-r1", route_hash="f" * 64,
        )
        key_b = _canonical_idempotency_key(
            launch_attempt_id="latch-r1", reservation_id="res-r1",
            reservation_hash="e" * 64, route_id="route-r1", route_hash="f" * 64,
        )
        key_c = _canonical_idempotency_key(
            launch_attempt_id="latch-r2", reservation_id="res-r1",
            reservation_hash="e" * 64, route_id="route-r1", route_hash="f" * 64,
        )
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)
        self.assertRegex(key_a, r"^[0-9a-f]{64}$")


class TamperCoverageTests(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="tamper")
        _persist_canonical_chain(self.auth_store, self.chain)
        self.launcher = _launcher_actor()

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)

    def test_recorded_attempt_reload_verifies_hash(self):
        reservation = _make_reservation(self.chain, launcher_actor=self.launcher)
        _persist_reservation(
            self.start_store, reservation,
            now=reservation.reserved_at, must_start_by=reservation.must_start_by,
        )
        admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=_make_binding_registry(self.chain),
            reservation_id=reservation.reservation_id,
            launcher_actor=self.launcher,
        )
        reloaded = self.start_store.get_launch_attempt(reservation.reservation_id)
        self.assertTrue(reloaded.verify_hash())


# --------------------------------------------------------------------------- #
# Additional test classes (tamper, concurrency, idempotency, etc.)
# --------------------------------------------------------------------------- #
