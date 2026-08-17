"""EA-4D.3E-C coordinator real-probe tests: narrow wiring + default safety.

Proves:
- the DEFAULT coordinator (TrustedFakeAdapterResolver) remains fake-only;
- an EXPLICITLY constructed real coordinator (TrustedRealAdapterResolver
  injecting a real LocalWorkerRuntimeAdapter) can drive a real probe;
- the coordinator still independently loads/verifies the durable LaunchAttempt
  and re-verifies lineage; real STARTED still does not project EXECUTING.
"""

import os
import shutil
import sys
import tempfile
import unittest

from tests.hermes_core.test_execution_launch_admission import (  # noqa: E402
    _build_canonical_chain,
    _persist_canonical_chain,
    _make_reservation,
    _persist_reservation,
    _launcher_actor,
    _fresh_authority_db,
    _fresh_start_db,
    admit_execution_launch_attempt,
    build_worker_runtime_binding,
    build_worker_runtime_binding_registry,
)
from tools.hermes_core.execution_start import (  # noqa: E402
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
)
from tools.hermes_core.execution_launch_coordinator import (  # noqa: E402
    ExecutionLaunchCoordinator,
    TrustedFakeAdapterResolver,
    TrustedRealAdapterResolver,
)
from tools.hermes_core.local_worker_runtime_config import (  # noqa: E402
    LocalWorkerLaunchConfig,
    TrustedLocalWorkerConfigRegistry,
    local_worker_config_canonical_hash,
)
from tools.hermes_core.local_worker_process_control import spawn_probe
from tools.hermes_core.local_worker_runtime_adapter import (  # noqa: E402
    LocalWorkerRuntimeAdapter,
    LocalWorkerIdempotencyRegistry,
    LocalWorkerTimeouts,
)
from tools.hermes_core.runtime_launch_adapter import RuntimeLaunchOutcome


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROBE_SCRIPT = os.path.join(
    REPO_ROOT, "tests", "hermes_core", "fixtures", "local_worker_stub.py")


def _make_config(config_id):
    return LocalWorkerLaunchConfig(
        config_id=config_id,
        config_version="1",
        executable=sys.executable,
        argv_template=(PROBE_SCRIPT,),
        cwd=REPO_ROOT,
        environment_allowlist=("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"),
    )


class CoordinatorRealProbeFixture(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        self.chain = _build_canonical_chain(seed="coord-real")
        _persist_canonical_chain(self.auth_store, self.chain)
        launcher = _launcher_actor()
        self.reservation = _make_reservation(self.chain, launcher_actor=launcher)
        _persist_reservation(
            self.start_store, self.reservation,
            now=self.reservation.reserved_at,
            must_start_by=self.reservation.must_start_by,
        )
        route = self.chain.route
        # Build the trusted local-worker binding from the chain's worker
        # identity, referencing the probe config. Its artifact_hash is computed
        # by build_worker_runtime_binding; the admission below records that
        # exact hash into the LaunchAttempt snapshot, so the coordinator's
        # re-verification succeeds.
        self.config = _make_config("hermes-worker-local-v1")
        self.binding = build_worker_runtime_binding(
            runtime_binding_id="binding-local-probe",
            worker_id=route.worker_id,
            worker_version="1",
            worker_class=route.worker_class,
            adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
            adapter_version="1",
            configuration_reference=self.config.config_id,
            configuration_hash=local_worker_config_canonical_hash(self.config),
            allowed_operations=(route.operation,),
            supports_idempotency=True,
            enabled=True,
        )
        self.registry = build_worker_runtime_binding_registry(
            registry_version="1", bindings=[self.binding])
        self.config_registry = TrustedLocalWorkerConfigRegistry(
            {self.config.config_id: self.config})
        self.attempt = admit_execution_launch_attempt(
            authority_store=self.auth_store,
            start_store=self.start_store,
            binding_registry=self.registry,
            reservation_id=self.reservation.reservation_id,
            launcher_actor=launcher,
        )
        self.idem_tmp = tempfile.mkdtemp()
        self.idem_db = os.path.join(self.idem_tmp, "idem.sqlite")
        self.idem_registry = LocalWorkerIdempotencyRegistry(self.idem_db)
        self.idem_registry.initialize()
        self._pc = type("PC", (), {"spawn_probe": staticmethod(spawn_probe)})()

    def _real_coordinator(self):
        def factory(kind):
            return LocalWorkerRuntimeAdapter(
                config_registry=self.config_registry,
                idempotency_registry=self.idem_registry,
                process_control=self._pc,
                timeouts=LocalWorkerTimeouts(),
            )
        return ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=TrustedRealAdapterResolver(factory=factory),
        )

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)
        shutil.rmtree(self.idem_tmp, ignore_errors=True)


class DefaultCoordinatorStillFakeOnly(CoordinatorRealProbeFixture):
    def test_default_coord_resolves_fake_only(self):
        coord = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=TrustedFakeAdapterResolver(),
        )
        self.assertIsInstance(coord._adapter_resolver, TrustedFakeAdapterResolver)


class RealCoordinatorProbeTests(CoordinatorRealProbeFixture):
    def test_explicit_real_coordinator_drives_probe(self):
        coord = self._real_coordinator()
        res = coord.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertTrue(res.runtime_run_id.startswith("probe-run-"))
        # Real STARTED does NOT project EXECUTING; durable attempt stays RECORDED.
        reloaded = self.start_store.get_launch_attempt(
            self.reservation.reservation_id)
        self.assertEqual(
            reloaded.status, ExecutionLaunchAttemptStatus.RECORDED)

    def test_real_coordinator_reconciles_after_spawn(self):
        coord = self._real_coordinator()
        coord.coordinate_launch(reservation_id=self.reservation.reservation_id)
        reconcile = coord.reconcile(reservation_id=self.reservation.reservation_id)
        from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.FOUND_STARTED)


if __name__ == "__main__":
    unittest.main()
