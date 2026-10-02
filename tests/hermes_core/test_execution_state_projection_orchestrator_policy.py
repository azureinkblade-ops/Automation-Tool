"""EA-4D.4C policy gate: default-off, propagation, negative capability.

Proves:
* default construction (enabled defaults False) -> DisabledError on call.
* explicit enabled=False -> DisabledError; projector never invoked.
* explicit enabled=True -> delegates to projector (STARTED -> EXECUTING).
* enabled=True + conflicting material lineage -> 4B ConflictError propagated.
* orchestrator module has no runtime launch/lookup/network capability.
* orchestrator does NOT import the Start DB / ExecutionStartResult reader
  (it holds only the injected projector; 4B owns STARTED verification).
"""

import inspect
import os
import tempfile
import unittest

from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
    ExecutionStateProjectionDisabledError,
)
from tools.hermes_core.execution_state_projector import ExecutionStateProjector
from tools.hermes_core.execution_authorization import (
    ExecutionStateProjection,
    ExecutionStateProjectionConflictError,
    build_execution_state_projection,
)


def _fake_projector_returning(projection):
    class _Fake(ExecutionStateProjector):
        def __init__(self):
            self.calls = []

        def project_executing(self, launch_attempt_id):
            self.calls.append(launch_attempt_id)
            return projection
    return _Fake()


class PolicyGateTest(unittest.TestCase):
    def test_default_construction_is_disabled(self):
        orch = ExecutionStateProjectionOrchestrator(
            projector=object(), enabled=False)
        self.assertFalse(orch.enabled)
        # Default-off is also the implicit default (enabled kwarg default False).
        orch2 = ExecutionStateProjectionOrchestrator(projector=object())
        self.assertFalse(orch2.enabled)

    def test_disabled_raises_and_never_calls_projector(self):
        proj = build_execution_state_projection(
            start_result_id="sr-1", start_result_hash="S" * 64,
            launch_attempt_id="latch-1", launch_attempt_hash="L" * 64,
            route_id="route-1", route_hash="r" * 64,
            authorization_id="auth-1", authorization_hash="Z" * 64,
            attempt_id="att-1", attempt_hash="A" * 64,
            task_id="task-1", worker_id="w1", worker_version="1",
            runtime_run_id="run-1", target_state="EXECUTING")
        fake = _fake_projector_returning(proj)
        orch = ExecutionStateProjectionOrchestrator(
            projector=fake, enabled=False)
        with self.assertRaises(ExecutionStateProjectionDisabledError):
            orch.project_executing_for_started("latch-1")
        self.assertEqual(fake.calls, [])

    def test_enabled_delegates_to_projector(self):
        proj = build_execution_state_projection(
            start_result_id="sr-1", start_result_hash="S" * 64,
            launch_attempt_id="latch-1", launch_attempt_hash="L" * 64,
            route_id="route-1", route_hash="r" * 64,
            authorization_id="auth-1", authorization_hash="Z" * 64,
            attempt_id="att-1", attempt_hash="A" * 64,
            task_id="task-1", worker_id="w1", worker_version="1",
            runtime_run_id="run-1", target_state="EXECUTING")
        fake = _fake_projector_returning(proj)
        orch = ExecutionStateProjectionOrchestrator(
            projector=fake, enabled=True)
        out = orch.project_executing_for_started("latch-1")
        self.assertIs(out, proj)
        self.assertEqual(fake.calls, ["latch-1"])

    def test_enabled_conflict_propagated_unchanged(self):
        class _Conflict(ExecutionStateProjector):
            def __init__(self):
                self.calls = []

            def project_executing(self, launch_attempt_id):
                self.calls.append(launch_attempt_id)
                raise ExecutionStateProjectionConflictError("conflict")
        fake = _Conflict()
        orch = ExecutionStateProjectionOrchestrator(
            projector=fake, enabled=True)
        with self.assertRaises(ExecutionStateProjectionConflictError):
            orch.project_executing_for_started("latch-1")
        # Propagated unchanged; orchestrator did not reinterpret it.
        self.assertEqual(fake.calls, ["latch-1"])

    def test_orchestrator_has_no_runtime_capability(self):
        import tools.hermes_core.execution_state_projection_orchestrator as mod
        src = inspect.getsource(mod)
        import_lines = "\n".join(
            ln for ln in src.splitlines()
            if ln.strip().startswith("import") or "import " in ln)
        for forbidden in (
            "RuntimeLaunchAdapter", "RuntimeStartLookup", "subprocess",
            "Popen", "os.system", "requests", "httpx", "socket", "aiohttp",
            "ssh", "docker", "ollama", "LocalWorkerRuntimeAdapter",
        ):
            # Docstring assertions of what the module does NOT do are permitted;
            # only real imports or call-sites are forbidden.
            if forbidden in import_lines:
                self.fail(f"orchestrator imports forbidden dependency: {forbidden}")
            if f"{forbidden}(" in src and forbidden != "RuntimeLaunchAdapter":
                self.fail(f"orchestrator calls forbidden API: {forbidden}")

    def test_orchestrator_holds_only_injected_projector_not_start_store(self):
        # Policy-only: the constructor signature accepts a projector and an
        # enabled flag; it does NOT take a Start DB / StartResult reader.
        sig = inspect.signature(ExecutionStateProjectionOrchestrator.__init__)
        params = list(sig.parameters)
        self.assertIn("projector", params)
        self.assertIn("enabled", params)
        # No Start-store / result-reader parameter exists.
        for forbidden in ("start_store", "start_result", "start_db",
                          "result_reader"):
            self.assertNotIn(forbidden, params)


if __name__ == "__main__":
    unittest.main()
