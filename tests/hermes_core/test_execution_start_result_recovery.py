"""EA-4D.4A: crash recovery tests (Crash A1/A2/A3, B, C).

Proves reconciliation semantics from a read-only lookup dependency:
A1 STARTED -> FOUND_STARTED -> persist STARTED
A2 durable FAILED -> FOUND_FAILED -> persist FAILED
A3 transient pre-delivery FAILED -> lost before persistence -> NOT_FOUND ->
   unresolved, no fabricated FAILED
B persisted response-loss -> replay returns same row (no duplicate)
C persisted result does NOT project EXECUTING (no projector on the service)
No runtime launch, no subprocess, no network, no new LaunchAttempt.
"""

import os
import tempfile
import unittest

from tools.hermes_core.execution_start import ExecutionStartOutcome
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService)
from tools.hermes_core.runtime_launch_adapter import (
    RuntimeLookupOutcome, RuntimeLookupResult)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore)

from tests.hermes_core.test_execution_start_result_service import (
    _reservation, _attempt, _evidence)


class _Lookup:
    def __init__(self, outcome, run_id=None, error_code=None, error_summary=None):
        self._outcome = outcome
        self._run_id = run_id
        self._error_code = error_code
        self._error_summary = error_summary

    def lookup(self, idempotency_key):
        return RuntimeLookupResult(
            outcome=self._outcome, runtime_run_id=self._run_id,
            error_code=self._error_code, error_summary=self._error_summary)


class RecoveryFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "start.db")
        self.store = SQLiteExecutionStartStore(self.db)
        self.store.migrate_to_v3()
        self.store.record_reservation(reservation=_reservation(), now="2024-01-01T00:00:00Z")
        self.store.record_launch_attempt(attempt=_attempt(), now="2024-01-01T00:00:00Z")

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def svc_with(self, outcome, **kw):
        return ExecutionStartResultService(self.store, _Lookup(outcome, **kw))


class CrashA1Tests(RecoveryFixture):
    def test_started_recovery_persists_started(self):
        svc = self.svc_with(RuntimeLookupOutcome.FOUND_STARTED, run_id="run-1")
        res = svc.reconcile_start_result("latch-1")
        self.assertIsNotNone(res)
        self.assertEqual(res.outcome, ExecutionStartOutcome.STARTED)
        self.assertEqual(res.runtime_run_id, "run-1")


class CrashA2Tests(RecoveryFixture):
    def test_durable_failed_recovery_persists_failed(self):
        svc = self.svc_with(RuntimeLookupOutcome.FOUND_FAILED,
                            error_code="WORKER_REJECTED",
                            error_summary="rejected by worker")
        res = svc.reconcile_start_result("latch-1")
        self.assertIsNotNone(res)
        self.assertEqual(res.outcome, ExecutionStartOutcome.FAILED)
        self.assertEqual(res.error_code, "WORKER_REJECTED")


class CrashA3Tests(RecoveryFixture):
    def test_transient_failed_lost_before_persistence_unresolved(self):
        # The durable registry reports NOT_FOUND_AUTHORITATIVE -> no result.
        svc = self.svc_with(RuntimeLookupOutcome.NOT_FOUND_AUTHORITATIVE)
        res = svc.reconcile_start_result("latch-1")
        self.assertIsNone(res)
        self.assertIsNone(self.store.get_execution_start_result("latch-1"))


class CrashBTests(RecoveryFixture):
    def test_persisted_response_loss_replay_returns_same_row(self):
        svc = self.svc_with(RuntimeLookupOutcome.FOUND_STARTED, run_id="run-1")
        first = svc.reconcile_start_result("latch-1")
        # Simulate caller never receiving the acknowledgement; reconcile again.
        second = svc.reconcile_start_result("latch-1")
        self.assertEqual(first.start_result_id, second.start_result_id)
        count = self.store._conn.execute(
            "SELECT COUNT(*) FROM execution_start_results").fetchone()[0]
        self.assertEqual(count, 1)


class CrashCTests(RecoveryFixture):
    def test_persisted_result_does_not_project_executing(self):
        svc = self.svc_with(RuntimeLookupOutcome.FOUND_STARTED, run_id="run-1")
        res = svc.reconcile_start_result("latch-1")
        self.assertIsNotNone(res)
        # The service has no EXECUTING projector; the result remains STARTED,
        # not EXECUTING. (EXECUTING is a separate, unauthorized 4B stage.)
        self.assertEqual(res.outcome, ExecutionStartOutcome.STARTED)
        self.assertFalse(hasattr(svc, "project_executing"))
        self.assertFalse(hasattr(svc, "set_executing"))


if __name__ == "__main__":
    unittest.main()
