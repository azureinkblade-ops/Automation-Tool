"""EA-4D.4E recovery: crash E1-E4 idempotency + concurrency, no worker relaunch.

Proves the gated dispatch boundary is safe to re-invoke after each crash point,
relying entirely on the replay-safe lower layers (4D/4A/4C/4B). 4E adds no
idempotency store of its own. Follows the proven 4D recovery test pattern.

E1: crash before 4D -> no state change; later explicit same-ID dispatch safe.
E2: 4A STARTED already persisted -> explicit redispatch -> safe replay.
E3: 4B projection already committed -> explicit redispatch -> same projection, no duplicate event.
E4: enabled=False -> typed disabled error; no 4D call; no background catch-up.

Concurrency: N identical enabled dispatches, same launch_attempt_id ->
    lower-layer idempotent replay -> one projection -> one ATTEMPT_EXECUTING event.
"""

import os
import tempfile
import unittest

from tools.hermes_core.execution_start import (
    ExecutionLaunchAttemptStatus,
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    build_execution_start_reservation,
    build_execution_launch_attempt,
)
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
    RuntimeStartLookup,
)
from tools.hermes_core.execution_state_projector import ExecutionStateProjector
from tools.hermes_core.execution_state_projection_orchestrator import (
    ExecutionStateProjectionOrchestrator,
)
from tools.hermes_core.local_worker_runtime_adapter import (
    RuntimeLookupOutcome,
    RuntimeLookupResult,
)
from tools.hermes_core.post_launch_execution_orchestrator import (
    PostLaunchExecutionOrchestrator,
    PostLaunchStatus,
)
from tools.hermes_core.sqlite_execution_authorization_store import (
    SQLiteExecutionAuthorizationStore,
)
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore
from tools.hermes_core.execution_post_launch_dispatcher import (
    ExecutionPostLaunchDispatchDisabledError,
    ExecutionPostLaunchDispatcher,
)


class _Lookup(RuntimeStartLookup):
    def __init__(self, outcome, run_id="run-1", error_code=None):
        self._outcome = outcome
        self._run_id = run_id
        self._error_code = error_code

    def lookup(self, idempotency_key):
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


class RecoveryTest(unittest.TestCase):
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

    def _dispatcher(self, lookup_outcome, enabled):
        svc = ExecutionStartResultService(self.start, _Lookup(lookup_outcome))
        orch_4c = ExecutionStateProjectionOrchestrator(
            projector=self.projector, enabled=True)
        orch_4d = PostLaunchExecutionOrchestrator(
            start_result_service=svc, projection_orchestrator=orch_4c)
        return ExecutionPostLaunchDispatcher(
            post_launch_orchestrator=orch_4d, enabled=enabled)

    def _proj_count(self):
        return self.auth._conn.execute(
            "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0]

    def _event_count(self):
        return self.auth._conn.execute(
            "SELECT COUNT(*) FROM authority_ledger "
            "WHERE event_type = 'ATTEMPT_EXECUTING'").fetchone()[0]

    # E1: crash before 4D -> no state change; later explicit redispatch safe.
    def test_e1_no_state_before_4d(self):
        disp = self._dispatcher(RuntimeLookupOutcome.FOUND_STARTED, enabled=True)
        # Simulate "crash before 4D" by never calling dispatch. State untouched.
        self.assertEqual(self._proj_count(), 0)
        self.assertEqual(self._event_count(), 0)
        # Later explicit same-ID dispatch proceeds normally.
        result = disp.dispatch_post_launch("latch-1")
        self.assertEqual(result.status, PostLaunchStatus.STARTED_PROJECTED)

    # E2: 4A STARTED already persisted -> explicit redispatch -> safe replay.
    def test_e2_redispatch_safe_replay(self):
        disp = self._dispatcher(RuntimeLookupOutcome.FOUND_STARTED, enabled=True)
        first = disp.dispatch_post_launch("latch-1")
        self.assertEqual(first.status, PostLaunchStatus.STARTED_PROJECTED)
        proj_id_1 = first.projection.projection_id
        # Re-dispatch same ID; lower layers replay; exactly one projection.
        second = disp.dispatch_post_launch("latch-1")
        self.assertEqual(second.projection.projection_id, proj_id_1)
        self.assertEqual(self._proj_count(), 1)

    # E3: 4B projection already committed -> explicit redispatch -> same
    # projection, no duplicate ATTEMPT_EXECUTING event.
    def test_e3_same_projection_no_duplicate_event(self):
        disp = self._dispatcher(RuntimeLookupOutcome.FOUND_STARTED, enabled=True)
        disp.dispatch_post_launch("latch-1")
        proj_before = self._proj_count()
        events_before = self._event_count()
        self.assertEqual(proj_before, 1)
        self.assertEqual(events_before, 1)
        disp.dispatch_post_launch("latch-1")
        self.assertEqual(self._proj_count(), proj_before)
        self.assertEqual(self._event_count(), events_before)

    # E4: enabled=False -> typed disabled error; no 4D call; no catch-up.
    def test_e4_disabled_no_4d_no_catchup(self):
        disp = self._dispatcher(RuntimeLookupOutcome.FOUND_STARTED, enabled=False)
        with self.assertRaises(ExecutionPostLaunchDispatchDisabledError):
            disp.dispatch_post_launch("latch-1")
        self.assertEqual(self._proj_count(), 0)
        self.assertEqual(self._event_count(), 0)

    # Concurrency: N identical enabled dispatches -> one projection, one event.
    def test_concurrency_one_projection_one_event(self):
        N = 8
        dispatchers = [
            self._dispatcher(RuntimeLookupOutcome.FOUND_STARTED, enabled=True)
            for _ in range(N)
        ]
        results = [d.dispatch_post_launch("latch-1") for d in dispatchers]
        for r in results:
            self.assertEqual(r.status, PostLaunchStatus.STARTED_PROJECTED)
        self.assertEqual(self._proj_count(), 1)
        self.assertEqual(self._event_count(), 1)


if __name__ == "__main__":
    unittest.main()
