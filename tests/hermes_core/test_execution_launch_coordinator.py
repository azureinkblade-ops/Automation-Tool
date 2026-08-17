"""EA-4D.3D tests: production launch coordinator against the deterministic fake.

Reuses the proven EA-4D.3B canonical-chain fixture helpers (imported from
test_execution_launch_admission) so the coordinator is exercised against real
persisted authority + start artifacts.

Invariant preserved: LAUNCH_ATTEMPT_RECORDED != WORKER STARTED. The coordinator
invokes only the deterministic fake adapter; it never persists
ExecutionStartResult, never projects EXECUTING, and never creates a new
LaunchAttempt.
"""

import inspect
import os
import shutil
import tempfile
import unittest

# Reuse the frozen 3B canonical-chain fixture helpers (no duplication; stays
# within the 3-new-file budget: 1 production + 2 test modules).
from tests.hermes_core.test_execution_launch_admission import (  # noqa: E402
    _build_canonical_chain,
    _persist_canonical_chain,
    _make_reservation,
    _persist_reservation,
    _make_binding_registry,
    _launcher_actor,
    _fresh_authority_db,
    _fresh_start_db,
    WorkerRuntimeAdapterKind,
    ExecutionAuthorizationScope,
    build_worker_runtime_binding,
    build_worker_runtime_binding_registry,
)

from tools.hermes_core.execution_launch_admission_service import (  # noqa: E402
    admit_execution_launch_attempt,
)
from tools.hermes_core.execution_launch_coordinator import (  # noqa: E402
    ExecutionLaunchCoordinator,
    LaunchCoordinationFailClosedError,
    LaunchCoordinationIntegrityError,
    TrustedFakeAdapterResolver,
)
from tools.hermes_core.runtime_launch_adapter import (  # noqa: E402
    RuntimeLaunchOutcome,
    RuntimeLookupOutcome,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (  # noqa: E402
    DeterministicFakeRuntimeAdapter,
    FakeLaunchScript,
)


class CoordinatorFixture:
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="coord")
        _persist_canonical_chain(self.auth_store, self.chain)
        launcher = _launcher_actor()
        self.reservation = _make_reservation(self.chain, launcher_actor=launcher)
        _persist_reservation(
            self.start_store, self.reservation,
            now=self.reservation.reserved_at,
            must_start_by=self.reservation.must_start_by,
        )
        self.registry = _make_binding_registry(self.chain)
        self.attempt = admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=self.registry,
            reservation_id=self.reservation.reservation_id,
            launcher_actor=launcher,
        )
        self.coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
        )

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)


class CoordinatorHappyPathTests(CoordinatorFixture, unittest.TestCase):
    def test_happy_fake_started_coordination(self):
        res = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertTrue(res.runtime_run_id)
        # STARTED does not authorize EXECUTING; durable attempt stays RECORDED.
        reloaded = self.start_store.get_launch_attempt(
            self.reservation.reservation_id)
        from tools.hermes_core.execution_start import ExecutionLaunchAttemptStatus
        self.assertEqual(reloaded.status, ExecutionLaunchAttemptStatus.RECORDED)

    def test_failed_coordination_definitive_non_start(self):
        adapter = DeterministicFakeRuntimeAdapter()
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(adapter),
        )
        adapter._script = FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.FAILED, error_code="REJECT")
        res = coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.FAILED)
        self.assertIsNone(res.runtime_run_id)

    def test_unknown_coordination_ambiguous(self):
        adapter = DeterministicFakeRuntimeAdapter()
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(adapter),
        )
        adapter._script = FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN)
        res = coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)


class CoordinatorLoadsDurableAttemptTests(CoordinatorFixture, unittest.TestCase):
    def test_coordinator_loads_durable_attempt_not_caller_artifact(self):
        # The coordinator API exposes only reservation_id; there is no parameter
        # to inject a caller-constructed LaunchAttempt.
        params = list(inspect.signature(
            ExecutionLaunchCoordinator.coordinate_launch).parameters)
        self.assertEqual(params, ["self", "reservation_id"])
        res = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)

    def test_corrupted_launch_attempt_rejected(self):
        # Tamper the persisted row so integrity verification fails closed.
        conn = self.start_store._conn
        conn.execute(
            "UPDATE execution_launch_attempts SET route_id = 'tampered' "
            "WHERE reservation_id = ?", (self.reservation.reservation_id,))
        conn.commit()
        with self.assertRaises(LaunchCoordinationIntegrityError):
            self.coordinator.coordinate_launch(
                reservation_id=self.reservation.reservation_id)


class CoordinatorBindingRejectionTests(CoordinatorFixture, unittest.TestCase):
    def test_wrong_binding_worker_rejected(self):
        # Registry whose only binding has a different worker_id -> fail closed.
        bad_binding = build_worker_runtime_binding(
            runtime_binding_id="binding-other",
            worker_id="worker-other",
            worker_version="1",
            worker_class=self.chain.route.worker_class,
            adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference="hermes-worker-local-v1",
            configuration_hash="b" * 64,
            allowed_operations=[self.chain.route.operation],
            supports_idempotency=True,
            enabled=True,
        )
        bad_registry = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[bad_binding])
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=bad_registry,
        )
        with self.assertRaises(LaunchCoordinationFailClosedError):
            coord.coordinate_launch(
                reservation_id=self.reservation.reservation_id)

    def test_caller_cannot_substitute_adapter_kind(self):
        # A binding with a non-local adapter kind must be rejected by the
        # coordinator's trusted resolver (fake-only boundary), even if the
        # binding itself is otherwise valid. No untrusted adapter can be
        # substituted.
        bad_binding = build_worker_runtime_binding(
            runtime_binding_id="binding-http",
            worker_id=self.chain.route.worker_id,
            worker_version="1",
            worker_class=self.chain.route.worker_class,
            adapter_kind=WorkerRuntimeAdapterKind.HTTP_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference="hermes-worker-http-v1",
            configuration_hash="b" * 64,
            allowed_operations=[self.chain.route.operation],
            supports_idempotency=True,
            enabled=True,
        )
        bad_registry = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[bad_binding])
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=bad_registry,
        )
        with self.assertRaises(LaunchCoordinationFailClosedError):
            coord.coordinate_launch(
                reservation_id=self.reservation.reservation_id)

    def test_idempotency_key_preserved_no_override(self):
        # Coordinator passes the attempt's canonical key; the deterministic fake
        # derives a stable runtime_run_id from exactly that key (no
        # substitution/regeneration).
        res = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        attempt = self.start_store.get_launch_attempt(
            self.reservation.reservation_id)
        from tools.hermes_core.deterministic_fake_runtime_adapter import (
            _stable_run_id,
        )
        self.assertEqual(res.runtime_run_id, _stable_run_id(attempt.idempotency_key))


class CoordinatorReplayTests(CoordinatorFixture, unittest.TestCase):
    def test_same_launch_attempt_replay_no_new_logical_run(self):
        # Share one fake adapter instance to observe logical-run count.
        adapter = DeterministicFakeRuntimeAdapter()
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(adapter),
        )
        r1 = coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        r2 = coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)
        self.assertEqual(adapter.logical_run_count, 1)
        self.assertEqual(adapter.invocation_count, 2)

    def test_unknown_causes_no_automatic_relaunch(self):
        adapter = DeterministicFakeRuntimeAdapter()
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(adapter),
        )
        adapter._script = FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN)
        coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(adapter.logical_run_count, 1)


class CoordinatorDefaultPathTests(CoordinatorFixture, unittest.TestCase):
    """Default production path: the coordinator's own resolver owns one stable
    fake instance. Proves the production default preserves fake state across
    invocations (one logical fake operation per LaunchAttempt) and can reconcile
    via lookup(), without injecting a shared fake through _ConstResolver."""

    def test_default_two_launches_one_logical_run(self):
        r1 = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        r2 = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(r1.runtime_run_id, r2.runtime_run_id)
        fake = self.coordinator._adapter_resolver.adapter
        self.assertEqual(fake.logical_run_count, 1)
        self.assertEqual(fake.invocation_count, 2)

    def test_default_replay_no_second_logical_run(self):
        self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        fake = self.coordinator._adapter_resolver.adapter
        self.assertEqual(fake.logical_run_count, 1)

    def test_default_lookup_sees_prior_launch(self):
        self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        # Reconcile through the SAME default resolver/fake; it must observe the
        # state created by the earlier default-resolver launch.
        reconcile = self.coordinator.reconcile(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertTrue(reconcile.runtime_run_id)

    def test_default_unknown_no_new_logical_run(self):
        fake = self.coordinator._adapter_resolver.adapter
        fake._script = FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN)
        res = self.coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)
        self.assertEqual(fake.logical_run_count, 1)
        # Reconcile repeatedly; remains UNKNOWN, never relaunches.
        for _ in range(3):
            r = self.coordinator.reconcile(
                reservation_id=self.reservation.reservation_id)
            self.assertEqual(r.outcome, RuntimeLaunchOutcome.UNKNOWN)
        self.assertEqual(fake.logical_run_count, 1)


class _ConstResolver:
    """Test-only resolver returning a fixed adapter instance (shared fake)."""

    def __init__(self, adapter):
        self._adapter = adapter

    def resolve(self, adapter_kind):
        if adapter_kind != WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER:
            raise LaunchCoordinationFailClosedError("rejected in test resolver")
        return self._adapter


if __name__ == "__main__":
    unittest.main()
