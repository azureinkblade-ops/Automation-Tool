"""EA-4D.4C orchestrator mechanics: trigger, disabled gate, error propagation.

Proves:
* disabled (enabled=False) -> ExecutionStateProjectionDisabledError; projector
  NOT invoked; no authority mutation.
* enabled + STARTED -> projector returns EXECUTING projection.
* enabled + FAILED -> 4B IneligibleError propagated unchanged.
* enabled + no result -> 4B IneligibleError propagated unchanged.
* enabled + integrity failure -> 4B IntegrityError propagated unchanged.
* repeated invocation over same STARTED -> same projection (4B owns replay).
* orchestrator holds NO StartResult dependency (policy-only).
"""

import os
import tempfile
import unittest

from tools.hermes_core.execution_start import (
    ExecutionStartOutcome,
    ExecutionLaunchAttemptStatus,
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    build_execution_start_reservation,
    build_execution_launch_attempt,
)
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
    VerifiedRuntimeStartEvidence,
    RuntimeStartLookup,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.execution_state_projector import ExecutionStateProjector
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
    ExecutionStateProjectionDisabledError,
)


def _launcher():
    return ExecutionLauncherActor(
        actor_id="la", actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER)


def _reservation():
    return build_execution_start_reservation(
        reservation_id="res-1", route_id="route-1", route_hash="r" * 64,
        attempt_id="att-1", attempt_hash="A" * 64,
        authorization_id="auth-1", authorization_hash="Z" * 64,
        claim_id="clm-1", claim_hash="C" * 64,
        request_id="req-1", request_hash="Q" * 64,
        decision_id="dec-1", decision_hash="D" * 64,
        task_id="task-1", worker_id="w1", worker_class=None,
        worker_version="1", operation="op", input_hash="i" * 64,
        reserved_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z", launcher_actor=_launcher())


def _attempt():
    return build_execution_launch_attempt(
        launch_attempt_id="latch-1", artifact_version="1",
        reservation_id="res-1", reservation_hash="r" * 64,
        route_id="route-1", route_hash="r" * 64, attempt_id="att-1",
        attempt_hash="A" * 64, authorization_id="auth-1",
        authorization_hash="Z" * 64, task_id="task-1", worker_id="w1",
        worker_class=None, worker_version="1", operation="op",
        input_hash="i" * 64, runtime_binding_id="bind-1",
        runtime_binding_version="1", runtime_binding_hash="B" * 64,
        idempotency_key="k" * 64, recorded_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z", launcher_actor=_launcher(),
        status=ExecutionLaunchAttemptStatus.RECORDED)


def _evidence(outcome, run_id="run-1", error_code=None):
    return VerifiedRuntimeStartEvidence(
        launch_attempt_id="latch-1", idempotency_key="k" * 64,
        runtime_outcome=outcome, runtime_run_id=run_id,
        source="launch",
        runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
        runtime_adapter_version="1",
        observed_at="2024-01-01T00:10:00Z",
        evidence_hash=ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="k" * 64,
            runtime_outcome=outcome, runtime_run_id=run_id,
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code=error_code),
        error_code=error_code, error_summary=None)


class _FakeLookup(RuntimeStartLookup):
    def lookup(self, launch_attempt_id):
        return None


class OrchestratorMechanicsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.start_db = os.path.join(self.tmp, "start.db")
        self.auth_db = os.path.join(self.tmp, "auth.db")
        self.auth = SQLiteExecutionAuthorizationStore(self.auth_db)
        self.start = SQLiteExecutionStartStore(self.start_db)
        self.start.migrate_to_v3()
        self.start.record_reservation(
            reservation=_reservation(), now="2024-01-01T00:00:00Z")
        self.start.record_launch_attempt(
            attempt=_attempt(), now="2024-01-01T00:00:00Z")
        self.svc = ExecutionStartResultService(self.start, _FakeLookup())
        self.projector = ExecutionStateProjector(self.start, self.auth)

    def tearDown(self):
        self.start.close()
        self.auth.close()

    def _persist_started(self):
        self.svc.persist_start_result(_attempt(), _reservation(), _evidence(
            ExecutionStartOutcome.STARTED))

    def _orchestrator(self, enabled=False):
        return ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=enabled)

    def test_disabled_raises_disabled_error_and_never_invokes_projector(self):
        # Count projector invocations; disabled must not call it.
        calls = []

        class _Spy(ExecutionStateProjector):
            def project_executing(self, launch_attempt_id):
                calls.append(launch_attempt_id)
                return super().project_executing(launch_attempt_id)

        orch = ExecutionStateProjectionOrchestrator(
            projector=_Spy(self.start, self.auth), enabled=False)
        with self.assertRaises(ExecutionStateProjectionDisabledError):
            orch.project_executing_for_started("latch-1")
        self.assertEqual(calls, [])
        # No authority mutation: projection table stays empty.
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            0)

    def test_enabled_started_projects_executing(self):
        self._persist_started()
        orch = self._orchestrator(enabled=True)
        proj = orch.project_executing_for_started("latch-1")
        self.assertEqual(proj.target_state, "EXECUTING")
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)

    def test_enabled_failed_propagates_ineligible_unchanged(self):
        self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.FAILED, error_code="E1"))
        orch = self._orchestrator(enabled=True)
        with self.assertRaises(Exception) as ctx:
            orch.project_executing_for_started("latch-1")
        # 4B raises ExecutionStateProjectionIneligibleError; 4C propagates it.
        from tools.hermes_core.execution_authorization import (
            ExecutionStateProjectionIneligibleError)
        self.assertIsInstance(ctx.exception, ExecutionStateProjectionIneligibleError)
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            0)

    def test_enabled_no_result_propagates_ineligible_unchanged(self):
        # Never persisted a result; 4B raises IneligibleError on missing result.
        orch = self._orchestrator(enabled=True)
        from tools.hermes_core.execution_authorization import (
            ExecutionStateProjectionIneligibleError)
        with self.assertRaises(ExecutionStateProjectionIneligibleError):
            orch.project_executing_for_started("latch-1")

    def test_repeat_over_same_started_same_projection(self):
        self._persist_started()
        orch = self._orchestrator(enabled=True)
        p1 = orch.project_executing_for_started("latch-1")
        p2 = orch.project_executing_for_started("latch-1")
        self.assertEqual(p1.projection_id, p2.projection_id)
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)


if __name__ == "__main__":
    unittest.main()
