"""EA-4D.3D recovery + reconciliation tests (Crash-D / Crash-F + lookup).

These exercise the frozen crash semantics: reconciliation reuses the SAME
logical launch identity (idempotency key) and never creates a new
LaunchAttempt. A shared deterministic fake adapter models the persistent
runtime across the simulate-crash boundary.

Invariant preserved: LAUNCH_ATTEMPT_RECORDED != WORKER STARTED. Reconciliation
never relaunches and never projects EXECUTING.
"""

import ast
import os
import shutil
import tempfile
import unittest

from tests.hermes_core.test_execution_launch_admission import (  # noqa: E402
    _build_canonical_chain,
    _persist_canonical_chain,
    _make_reservation,
    _persist_reservation,
    _make_binding_registry,
    _launcher_actor,
    _fresh_authority_db,
    _fresh_start_db,
    admit_execution_launch_attempt,
)
from tools.hermes_core.execution_launch_coordinator import (  # noqa: E402
    ExecutionLaunchCoordinator,
    LaunchCoordinationFailClosedError,
)
from tools.hermes_core.runtime_launch_adapter import (  # noqa: E402
    RuntimeLaunchOutcome,
    RuntimeLookupOutcome,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (  # noqa: E402
    DeterministicFakeRuntimeAdapter,
    FakeLaunchScript,
)
from tools.hermes_core.execution_start import (  # noqa: E402
    ExecutionLaunchAttemptStatus,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _ConstResolver:
    def __init__(self, adapter):
        self._adapter = adapter

    def resolve(self, adapter_kind):
        if adapter_kind.name != "LOCAL_WORKER_ADAPTER":
            raise LaunchCoordinationFailClosedError("rejected in test resolver")
        return self._adapter


def _admit(scenario):
    """Persist a canonical chain, reserve, and admit a durable LaunchAttempt."""
    scenario.chain = _build_canonical_chain(seed="recover")
    _persist_canonical_chain(scenario.auth_store, scenario.chain)
    launcher = _launcher_actor()
    scenario.reservation = _make_reservation(
        scenario.chain, launcher_actor=launcher)
    _persist_reservation(
        scenario.start_store, scenario.reservation,
        now=scenario.reservation.reserved_at,
        must_start_by=scenario.reservation.must_start_by,
    )
    scenario.registry = _make_binding_registry(scenario.chain)
    scenario.attempt = admit_execution_launch_attempt(
        authority_store=scenario.auth_store,
        start_store=scenario.start_store,
        binding_registry=scenario.registry,
        reservation_id=scenario.reservation.reservation_id,
        launcher_actor=launcher,
    )


class RecoveryFixture(unittest.TestCase):
    def setUp(self):
        self.auth_tmp, self.auth_store = _fresh_authority_db()
        self.start_tmp, self.start_store = _fresh_start_db()
        _admit(self)

    def tearDown(self):
        self.auth_store.close()
        self.start_store.close()
        shutil.rmtree(self.auth_tmp, ignore_errors=True)
        shutil.rmtree(self.start_tmp, ignore_errors=True)


class CrashDTests(RecoveryFixture):
    def test_crash_d_recovery_with_not_found_authoritative(self):
        # Simulated crash BEFORE adapter invocation: a fresh coordinator (same
        # persistent fake runtime) reconciles first.
        shared_fake = DeterministicFakeRuntimeAdapter()
        coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(shared_fake),
        )
        reconcile = coordinator.reconcile(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(
            reconcile.reconciliation_state,
            RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
        # Same logical launch may be completed (no new admission artifact).
        res = coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertEqual(shared_fake.logical_run_count, 1)  # no duplicate run
        # Same launch_attempt_id and idempotency key; no new LaunchAttempt.
        self.assertEqual(res.launch_attempt_id, self.attempt.launch_attempt_id)


class CrashFTests(RecoveryFixture):
    def test_crash_f_recovery_with_found_started(self):
        shared_fake = DeterministicFakeRuntimeAdapter()
        coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(shared_fake),
        )
        first = coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(first.outcome, RuntimeLaunchOutcome.STARTED)
        # Simulate crash after the (simulated) response is lost; reconcile.
        reconcile = coordinator.reconcile(
            reservation_id=self.reservation.reservation_id)
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.FOUND_STARTED)
        # Recovered runtime_run_id equals the original deterministic id.
        self.assertEqual(reconcile.runtime_run_id, first.runtime_run_id)
        # No second logical fake launch; no replacement LaunchAttempt.
        self.assertEqual(shared_fake.logical_run_count, 1)
        self.assertEqual(
            reconcile.launch_attempt_id, self.attempt.launch_attempt_id)


class ReconciliationOutcomeTests(RecoveryFixture):
    def _coordinate_with(self, outcome):
        shared_fake = DeterministicFakeRuntimeAdapter()
        if outcome is not None:
            shared_fake._script = FakeLaunchScript(launch_outcome=outcome)
        coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(shared_fake),
        )
        res = coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        reconcile = coordinator.reconcile(
            reservation_id=self.reservation.reservation_id)
        return res, reconcile

    def test_reconciliation_found_failed(self):
        _, reconcile = self._coordinate_with(RuntimeLaunchOutcome.FAILED)
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.FOUND_FAILED)
        self.assertEqual(reconcile.outcome, RuntimeLaunchOutcome.FAILED)

    def test_reconciliation_unknown(self):
        _, reconcile = self._coordinate_with(RuntimeLaunchOutcome.UNKNOWN)
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.UNKNOWN)
        self.assertEqual(reconcile.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_recovered_started_uses_stable_original_run_id(self):
        first, reconcile = self._coordinate_with(RuntimeLaunchOutcome.STARTED)
        self.assertEqual(
            reconcile.reconciliation_state, RuntimeLookupOutcome.FOUND_STARTED)
        self.assertEqual(reconcile.runtime_run_id, first.runtime_run_id)

    def test_unknown_remains_unresolved_no_relaunch(self):
        shared_fake = DeterministicFakeRuntimeAdapter()
        shared_fake._script = FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN)
        coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
            adapter_resolver=_ConstResolver(shared_fake),
        )
        coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        # Reconcile repeatedly; never relaunch, never create a new logical run.
        for _ in range(3):
            r = coordinator.reconcile(
                reservation_id=self.reservation.reservation_id)
            self.assertEqual(r.outcome, RuntimeLaunchOutcome.UNKNOWN)
        self.assertEqual(shared_fake.logical_run_count, 1)


class NoDurableResultMutationTests(RecoveryFixture):
    def test_no_execution_start_result_no_executing_persisted(self):
        coordinator = ExecutionLaunchCoordinator(
            start_store=self.start_store,
            authority_store=self.auth_store,
            binding_registry=self.registry,
        )
        coordinator.coordinate_launch(
            reservation_id=self.reservation.reservation_id)
        # The durable LaunchAttempt status remains RECORDED (no EXECUTING); the
        # coordinator writes no result/session/status rows.
        reloaded = self.start_store.get_launch_attempt(
            self.reservation.reservation_id)
        self.assertEqual(
            reloaded.status, ExecutionLaunchAttemptStatus.RECORDED)


class CapabilityNegativeTests(unittest.TestCase):
    def test_coordinator_no_executable_capability(self):
        path = os.path.join(
            REPO_ROOT, "tools", "hermes_core", "execution_launch_coordinator.py")
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        forbidden_imports = {
            "subprocess", "os", "requests", "httpx", "urllib", "socket",
            "aiohttp", "playwright", "paramiko", "fabric", "docker", "ssh",
        }
        forbidden_calls = {
            "Popen", "system", "requests", "httpx", "urllib", "Playwright",
            "Ollama", "Docker", "SSH", "PowerShell", "cmd", "bash",
            "dispatch", "enqueue", "spawn", "execute_external",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden_imports)
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                self.assertNotIn(mod, forbidden_imports)
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(
                    node.func, "id", None)
                if name in forbidden_calls:
                    self.fail(f"forbidden call {name}")


if __name__ == "__main__":
    unittest.main()
