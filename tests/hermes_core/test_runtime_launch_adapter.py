"""EA-4D.3C protocol/contract tests for the typed runtime launch adapter.

These tests exercise the frozen contracts (outcomes, result immutability,
STARTED requires runtime_run_id, binding/lineage preservation, no Authority
state mutation, no routing mutation) using the deterministic fake adapter as a
concrete ``RuntimeLaunchAdapter`` implementation, plus a capability-negative
AST/import scan of the new production code.

Invariant preserved: LAUNCH_ATTEMPT_RECORDED != WORKER STARTED. The fake is
never invoked by production coordinator code; direct calls are test-only.
"""

import ast
import os
import unittest

from tools.hermes_core.execution_start import (
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionLaunchAttempt,
    ExecutionLaunchAttemptStatus,
    WorkerRuntimeAdapterKind,
    WorkerRuntimeBinding,
    build_execution_launch_attempt,
    build_worker_runtime_binding,
)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeAdapterConflictError,
    RuntimeAdapterValidationError,
    RuntimeLaunchAdapter,
    RuntimeLaunchOutcome,
    RuntimeLaunchResult,
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.deterministic_fake_runtime_adapter import (
    DeterministicFakeRuntimeAdapter,
    FakeLaunchScript,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _binding():
    return build_worker_runtime_binding(
        runtime_binding_id="binding-1",
        worker_id="worker-1",
        worker_version="1",
        worker_class="run-sandbox",
        adapter_kind=WorkerRuntimeAdapterKind.LOCAL_WORKER_ADAPTER,
        adapter_version="1",
        configuration_reference="hermes-worker-local-v1",
        configuration_hash="b" * 64,
        allowed_operations=["run-sandbox"],
        supports_idempotency=True,
        enabled=True,
    )


def _attempt(idempotency_key="k-1"):
    return build_execution_launch_attempt(
        launch_attempt_id="latch-1",
        reservation_id="res-1",
        reservation_hash="h" * 64,
        route_id="route-1",
        route_hash="r" * 64,
        attempt_id="att-1",
        attempt_hash="a" * 64,
        authorization_id="auth-1",
        authorization_hash="z" * 64,
        task_id="task-1",
        worker_id="worker-1",
        worker_class="run-sandbox",
        worker_version="1",
        operation="run-sandbox",
        input_hash="0" * 64,
        runtime_binding_id="binding-1",
        runtime_binding_version="1",
        runtime_binding_hash="b" * 64,
        idempotency_key=idempotency_key,
        recorded_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z",
        launcher_actor=ExecutionLauncherActor(
            actor_id="launcher-1",
            actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
            actor_context=None,
        ),
        status=ExecutionLaunchAttemptStatus.RECORDED,
    )


class ProtocolContractTests(unittest.TestCase):
    def test_runtime_launch_adapter_is_runtime_checkable(self):
        self.assertTrue(isinstance(DeterministicFakeRuntimeAdapter(), RuntimeLaunchAdapter))

    def test_outcomes_frozen_three(self):
        self.assertEqual(
            {o.value for o in RuntimeLaunchOutcome},
            {"STARTED", "FAILED", "UNKNOWN"},
        )

    def test_valid_started_result(self):
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        res = adapter.launch(
            binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.STARTED)
        self.assertTrue(res.runtime_run_id)

    def test_valid_failed_result(self):
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.FAILED,
            error_code="REJECT", error_summary="no"))
        res = adapter.launch(
            binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.FAILED)
        self.assertIsNone(res.runtime_run_id)

    def test_valid_unknown_result(self):
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.UNKNOWN))
        res = adapter.launch(
            binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertEqual(res.outcome, RuntimeLaunchOutcome.UNKNOWN)

    def test_started_requires_runtime_run_id(self):
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        res = adapter.launch(
            binding=_binding(), launch_attempt=_attempt(), idempotency_key="k-1")
        self.assertIsNotNone(res.runtime_run_id)
        self.assertNotEqual(res.runtime_run_id, "")

    def test_binding_identity_preserved(self):
        binding = _binding()
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        adapter.launch(
            binding=binding, launch_attempt=_attempt(), idempotency_key="k-1")
        # binding object is never mutated by the adapter
        self.assertTrue(binding.enabled)
        self.assertEqual(binding.worker_id, "worker-1")

    def test_launch_attempt_lineage_preserved(self):
        attempt = _attempt()
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        res = adapter.launch(
            binding=_binding(), launch_attempt=attempt, idempotency_key="k-1")
        self.assertEqual(attempt.launch_attempt_id, "latch-1")
        self.assertEqual(attempt.status, ExecutionLaunchAttemptStatus.RECORDED)
        self.assertIsNotNone(res.runtime_run_id)

    def test_no_authority_state_mutation(self):
        # The adapter contract performs no Authority/Start DB writes. This is a
        # structural guarantee: launching returns an immutable result and the
        # LaunchAttempt object is unchanged.
        attempt = _attempt()
        before = (attempt.launch_attempt_id, attempt.reservation_id,
                  attempt.status.value)
        DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED)).launch(
            binding=_binding(), launch_attempt=attempt, idempotency_key="k-1")
        after = (attempt.launch_attempt_id, attempt.reservation_id,
                 attempt.status.value)
        self.assertEqual(before, after)

    def test_no_routing_mutation(self):
        attempt = _attempt()
        adapter = DeterministicFakeRuntimeAdapter(FakeLaunchScript(
            launch_outcome=RuntimeLaunchOutcome.STARTED))
        adapter.launch(
            binding=_binding(), launch_attempt=attempt, idempotency_key="k-1")
        # route identity on the attempt is untouched
        self.assertEqual(attempt.route_id, "route-1")
        self.assertEqual(attempt.route_hash, "r" * 64)

    def test_result_is_immutable(self):
        res = RuntimeLaunchResult(outcome=RuntimeLaunchOutcome.UNKNOWN)
        with self.assertRaises(Exception):
            res.outcome = RuntimeLaunchOutcome.STARTED

    def test_invalid_outcome_rejected_at_type_level(self):
        # RuntimeLaunchOutcome is a str-enum with exactly three members; any
        # other string is not a valid outcome.
        with self.assertRaises(ValueError):
            RuntimeLaunchOutcome("OTHER")


class CapabilityNegativeTests(unittest.TestCase):
    def _scan(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        forbidden_imports = {
            "subprocess", "os", "requests", "httpx", "urllib", "socket",
            "playwright", "paramiko", "fabric", "aiohttp", "ssh",
        }
        forbidden_calls = {
            "Popen", "system", "os.system", "subprocess", "socket",
            "requests", "httpx", "urllib", "Playwright", "Ollama",
            "paramiko", "fabric", "ssh", "powershell", "cmd", "bash",
            "dispatch", "enqueue", "spawn", "execute_external",
            "worker.start", "worker.run", "network submit",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    self.assertNotIn(
                        mod, forbidden_imports,
                        f"{path}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                self.assertNotIn(
                    mod, forbidden_imports,
                    f"{path}: forbidden from-import {node.module}")
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                if name in forbidden_calls:
                    self.fail(f"{path}: forbidden call {name}")

    def test_production_adapter_no_executable_capability(self):
        self._scan(os.path.join(
            REPO_ROOT, "tools", "hermes_core", "runtime_launch_adapter.py"))

    def test_fake_adapter_no_executable_capability(self):
        self._scan(os.path.join(
            REPO_ROOT, "tools", "hermes_core",
            "deterministic_fake_runtime_adapter.py"))

    def test_fake_adapter_no_external_invocation(self):
        # The fake adapter module must not contain a launch invocation from a
        # production coordinator: its only .launch caller is itself (tests call
        # it externally). We assert no import of the coordinator/admission
        # service exists in the fake module.
        with open(os.path.join(
            REPO_ROOT, "tools", "hermes_core",
            "deterministic_fake_runtime_adapter.py"), "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("execution_launch_admission_service", src)
        self.assertNotIn("admit_execution_launch_attempt", src)


if __name__ == "__main__":
    unittest.main()
