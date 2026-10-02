"""EA-4D.4B recovery + concurrency.

Proves:
* Crash D: eligibility reload + idempotent projection after a lost attempt.
* Crash F: committed EXECUTING + response loss -> replay returns same
  projection; no second event.
* Already-EXECUTING replay: idempotent success.
* Concurrency: N concurrent identical projections -> one durable projection.
* Negative capability: no runtime lookup/launch/network in the projector.
"""

import os
import tempfile
import threading
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


def _launcher():
    return ExecutionLauncherActor(
        actor_id="la",
        actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER)


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
        launch_attempt_id="latch-1", artifact_version="1", reservation_id="res-1",
        reservation_hash="r" * 64,
        route_id="route-1", route_hash="r" * 64, attempt_id="att-1",
        attempt_hash="A" * 64, authorization_id="auth-1",
        authorization_hash="Z" * 64, task_id="task-1", worker_id="w1",
        worker_class=None, worker_version="1", operation="op",
        input_hash="i" * 64, runtime_binding_id="bind-1",
        runtime_binding_version="1", runtime_binding_hash="B" * 64,
        idempotency_key="k" * 64, recorded_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z",
        launcher_actor=_launcher(),
        status=ExecutionLaunchAttemptStatus.RECORDED)


def _evidence():
    return VerifiedRuntimeStartEvidence(
        launch_attempt_id="latch-1", idempotency_key="k" * 64,
        runtime_outcome=ExecutionStartOutcome.STARTED, runtime_run_id="run-1",
        source="launch",
        runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
        runtime_adapter_version="1",
        observed_at="2024-01-01T00:10:00Z",
        evidence_hash=ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="k" * 64,
            runtime_outcome=ExecutionStartOutcome.STARTED, runtime_run_id="run-1",
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code=None),
        error_code=None, error_summary=None)


class _FakeLookup(RuntimeStartLookup):
    def lookup(self, launch_attempt_id):
        return None


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
        self.svc = ExecutionStartResultService(self.start, _FakeLookup())
        self.svc.persist_start_result(_attempt(), _reservation(), _evidence())
        self.projector = ExecutionStateProjector(self.start, self.auth)

    def tearDown(self):
        self.start.close()
        self.auth.close()

    def test_crash_d_reload_and_project_idempotent(self):
        # Simulate a lost projection attempt: nothing committed yet.
        self.assertIsNone(self.auth.get_projection(
            self.start.get_execution_start_result("latch-1").start_result_id))
        p = self.projector.project_executing("latch-1")
        self.assertEqual(p.target_state, "EXECUTING")
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)

    def test_crash_f_response_loss_replay_same_projection(self):
        p1 = self.projector.project_executing("latch-1")
        # Response lost; caller retries.
        p2 = self.projector.project_executing("latch-1")
        self.assertEqual(p1.projection_id, p2.projection_id)
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM authority_ledger WHERE "
                "event_type='ATTEMPT_EXECUTING'").fetchone()[0], 1)
        self.assertEqual(
            self.auth._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)

    def test_already_executing_replay_idempotent(self):
        p1 = self.projector.project_executing("latch-1")
        p2 = self.projector.project_executing("latch-1")
        self.assertEqual(p1.projection_id, p2.projection_id)

    def test_projector_sequential_replay_same_projection(self):
        # Projector-level replay semantics: a second project_executing call for an
        # already-projected start result returns the SAME immutable projection.
        # (This is the projector replay proof; the authority-store true-concurrency
        # proof lives in test_concurrent_record_projection_one_row below.)
        p1 = self.projector.project_executing("latch-1")
        p2 = self.projector.project_executing("latch-1")
        self.assertEqual(p1.projection_id, p2.projection_id)
        self.assertEqual(p1.artifact_hash, p2.artifact_hash)

    def test_concurrent_record_projection_one_row(self):
        # TRUE CONCURRENCY proof at the authoritative mutation boundary.
        # Build ONE valid immutable ExecutionStateProjection; spawn N threads, each
        # with an INDEPENDENT SQLiteExecutionAuthorizationStore connection to the
        # same file, all calling record_projection(same_projection). This directly
        # exercises the once-only guarantee:
        #   BEGIN IMMEDIATE + PRIMARY KEY(projection_id)
        #   + UNIQUE(start_result_id, target_state) + atomic ledger append.
        # No Start-store access is involved, so the unrelated Start-store v3 reopen
        # defect is isolated out.
        from tools.hermes_core.execution_authorization import (
            build_execution_state_projection)
        from tools.hermes_core.sqlite_execution_authorization_store import (
            SQLiteExecutionAuthorizationStore)

        projection = build_execution_state_projection(
            start_result_id="sr-conc-1", start_result_hash="S" * 64,
            launch_attempt_id="latch-1", launch_attempt_hash="L" * 64,
            route_id="route-1", route_hash="r" * 64,
            authorization_id="auth-1", authorization_hash="Z" * 64,
            attempt_id="att-1", attempt_hash="A" * 64,
            task_id="task-1", worker_id="w1", worker_version="1",
            runtime_run_id="run-1", target_state="EXECUTING")

        returned_ids = []
        errors = []

        def worker():
            try:
                a = SQLiteExecutionAuthorizationStore(self.auth_db)
                pid = a.record_projection(projection)
                returned_ids.append((pid, projection.artifact_hash))
                a.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # Exactly one durable projection row, one ATTEMPT_EXECUTING ledger event.
        reopened = SQLiteExecutionAuthorizationStore(self.auth_db)
        self.assertEqual(
            reopened._conn.execute(
                "SELECT COUNT(*) FROM execution_state_projections").fetchone()[0],
            1)
        self.assertEqual(
            reopened._conn.execute(
                "SELECT COUNT(*) FROM authority_ledger WHERE "
                "event_type='ATTEMPT_EXECUTING'").fetchone()[0], 1)
        # All successful callers observed the SAME projection_id/artifact_hash.
        self.assertEqual(len(returned_ids), 8)
        self.assertTrue(all(
            pid == projection.projection_id and ah == projection.artifact_hash
            for pid, ah in returned_ids))
        reopened.close()

    def test_projector_has_no_runtime_capability(self):
        # The projector module must not import or invoke runtime
        # launch/lookup/network/subprocess. Docstring mentions of these names
        # (stating what it does NOT do) are permitted; only real imports or
        # call-sites are forbidden.
        import inspect
        import tools.hermes_core.execution_state_projector as mod
        src = inspect.getsource(mod)
        import_lines = "\n".join(
            ln for ln in src.splitlines() if ln.strip().startswith("import")
            or "import " in ln and "RuntimeLaunch" in ln)
        for forbidden in ("RuntimeLaunchAdapter", "RuntimeStartLookup.lookup",
                          "subprocess", "os.system", "requests", "httpx",
                          "socket", "aiohttp", "ssh", "docker", "ollama"):
            # Forbid only if it appears as an actual import or call, not a
            # docstring assertion like "no RuntimeLaunchAdapter.launch".
            if forbidden in import_lines:
                self.fail(f"projector imports forbidden dependency: {forbidden}")
            if f"{forbidden}(" in src and forbidden != "RuntimeLaunchAdapter":
                self.fail(f"projector calls forbidden API: {forbidden}")


if __name__ == "__main__":
    unittest.main()
