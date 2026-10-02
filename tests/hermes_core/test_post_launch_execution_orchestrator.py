"""EA-4D.4D orchestrator mechanics: trigger, statuses, error propagation.

Proves:
* STARTED + 4C enabled -> STARTED_PROJECTED (4C invoked, 4B projects).
* STARTED + 4C disabled -> STARTED_NOT_PROJECTED (DisabledError handled;
  4C NOT invoked; no authority mutation).
* FAILED -> FAILED_RECORDED (4C NOT called).
* non-definitive (4A returns None) -> PostLaunchExecutionError (no 4C).
* 4A unknown attempt -> 4A typed error propagates unchanged (no 4C).
* 4B conflict/integrity/ineligible -> propagate unchanged (NOT STARTED_NOT_PROJECTED).
* 4D holds no activation boolean (enabled lives on injected 4C).
* PostLaunchExecutionResult is in-memory (projection None for non-projected).
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
from tools.hermes_core.runtime_launch_adapter import RuntimeLookupOutcome
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
from tools.hermes_core.execution_authorization import (
    ExecutionStateProjectionConflictError,
)
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
    PostLaunchExecutionResult,
    PostLaunchExecutionError,
    PostLaunchStatus,
)


class _Lookup(RuntimeStartLookup):
    def __init__(self, outcome, run_id="run-1", error_code=None):
        self._outcome = outcome
        self._run_id = run_id
        self._error_code = error_code

    def lookup(self, idempotency_key):
        from tools.hermes_core.runtime_launch_adapter import RuntimeLookupResult
        return RuntimeLookupResult(
            outcome=self._outcome, runtime_run_id=self._run_id,
            error_code=self._error_code, error_summary=None)


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
        self.projector = ExecutionStateProjector(self.start, self.auth)

    def tearDown(self):
        self.start.close()
        self.auth.close()

    def _orchestrator(self, enabled=False):
        svc = ExecutionStartResultService(self.start, _Lookup(
            RuntimeLookupOutcome.FOUND_STARTED))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=enabled)
        return PostLaunchExecutionOrchestratorHolder(svc, orch_4c)

    def test_started_with_4c_enabled_projects(self):
        holder = self._orchestrator(enabled=True)
        res = holder.run_post_launch("latch-1")
        self.assertIsInstance(res, PostLaunchExecutionResult)
        self.assertEqual(res.status, PostLaunchStatus.STARTED_PROJECTED)
        self.assertIsNotNone(res.projection)
        # 4B committed exactly one projection.
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)

    def test_started_with_4c_disabled_returns_not_projected(self):
        holder = self._orchestrator(enabled=False)
        res = holder.run_post_launch("latch-1")
        self.assertEqual(res.status, PostLaunchStatus.STARTED_NOT_PROJECTED)
        self.assertIsNone(res.projection)
        # 4C never invoked: no projection row.
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            0)

    def test_failed_records_without_4c(self):
        svc = ExecutionStartResultService(self.start, _Lookup(
            RuntimeLookupOutcome.FOUND_FAILED, error_code="E1"))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=True)
        res = PostLaunchExecutionOrchestrator(
            start_result_service=svc,
            projection_orchestrator=orch_4c).run_post_launch("latch-1")
        self.assertEqual(res.status, PostLaunchStatus.FAILED_RECORDED)
        self.assertIsNone(res.projection)
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            0)

    def test_non_definitive_raises_post_launch_error(self):
        # NOT_FOUND_AUTHORITATIVE -> 4A returns None -> PostLaunchExecutionError.
        svc = ExecutionStartResultService(self.start, _Lookup(
            RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=True)
        with self.assertRaises(PostLaunchExecutionError):
            PostLaunchExecutionOrchestrator(
                start_result_service=svc,
                projection_orchestrator=orch_4c).run_post_launch("latch-1")

    def test_unknown_attempt_propagates_4a_error(self):
        from tools.hermes_core.execution_start_result_service import (
            ExecutionStartResultError)
        svc = ExecutionStartResultService(self.start, _Lookup(
            RuntimeLookupOutcome.FOUND_STARTED))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=True)
        with self.assertRaises(ExecutionStartResultError):
            PostLaunchExecutionOrchestrator(
                start_result_service=svc,
                projection_orchestrator=orch_4c).run_post_launch("does-not-exist")

    def test_4b_conflict_propagates_unchanged(self):
        # Force 4B to raise a conflict by injecting a conflict-raising projector.
        class _Conflict(ExecutionStateProjector):
            def project_executing(self, launch_attempt_id):
                raise ExecutionStateProjectionConflictError("conflict")

        svc = ExecutionStartResultService(self.start, _Lookup(
            RuntimeLookupOutcome.FOUND_STARTED))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=_Conflict(self.start, self.auth), enabled=True)
        with self.assertRaises(ExecutionStateProjectionConflictError):
            PostLaunchExecutionOrchestrator(
                start_result_service=svc,
                projection_orchestrator=orch_4c).run_post_launch("latch-1")

    def test_4d_holds_no_activation_boolean(self):
        # The orchestrator ctor takes only the injected services; no 'enabled'.
        import inspect
        sig = inspect.signature(PostLaunchExecutionOrchestrator.__init__)
        self.assertIn("start_result_service", sig.parameters)
        self.assertIn("projection_orchestrator", sig.parameters)
        self.assertNotIn("enabled", sig.parameters)


class PostLaunchExecutionOrchestratorHolder:
    """Small helper so test methods can call run_post_launch directly."""

    def __init__(self, svc, orch_4c):
        self._orch = PostLaunchExecutionOrchestrator(
            start_result_service=svc, projection_orchestrator=orch_4c)

    def run_post_launch(self, launch_attempt_id):
        return self._orch.run_post_launch(launch_attempt_id)


if __name__ == "__main__":
    unittest.main()
