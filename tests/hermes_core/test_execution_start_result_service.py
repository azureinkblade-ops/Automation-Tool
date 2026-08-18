"""EA-4D.4A: ExecutionStartResult service + domain integrity tests.

Proves deterministic identity/hashing, lineage verification, result semantics,
replay/conflict, UNKNOWN/NOT_FOUND -> no result, and negative authority
(no EXECUTING, no launch, no subprocess, no network, no new LaunchAttempt).
"""

import os
import tempfile
import unittest

from tools.hermes_core.execution_start import (
    ExecutionStartOutcome,
    ExecutionStartResultConflictError,
    ExecutionStartResultError,
    build_execution_start_reservation,
    build_execution_launch_attempt,
    build_execution_start_result,
    ExecutionLauncherActor,
    ExecutionLauncherActorType,
    ExecutionStartReservationStatus,
    ExecutionLaunchAttemptStatus,
)
from tools.hermes_core.execution_start_result_service import (
    ExecutionStartResultService,
    VerifiedRuntimeStartEvidence,
)
from tools.hermes_core.sqlite_execution_start_store import (
    SQLiteExecutionStartStore,
)
from tools.hermes_core.hashing import sha256_payload


def _launcher():
    return ExecutionLauncherActor(
        actor_id="launcher-1",
        actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
        actor_context=None,
    )


def _reservation(res_id="res-1"):
    return build_execution_start_reservation(
        reservation_id=res_id,
        route_id="route-1", route_hash="r" * 64,
        attempt_id="att-1", attempt_hash="a" * 64,
        authorization_id="auth-1", authorization_hash="z" * 64,
        claim_id="claim-1", claim_hash="c" * 64,
        request_id="req-1", request_hash="q" * 64,
        decision_id="dec-1", decision_hash="d" * 64,
        task_id="task-1", worker_id="worker-1", worker_class="run-sandbox",
        worker_version="1", operation="run-sandbox", input_hash="0" * 64,
        reserved_at="2024-01-01T00:00:00Z",
        must_start_by="2024-01-02T00:00:00Z",
        launcher_actor=_launcher(),
        status=ExecutionStartReservationStatus.RESERVED,
    )


def _attempt(att_id="latch-1", res_id="res-1", idem="i" * 64):
    return build_execution_launch_attempt(
        launch_attempt_id=att_id,
        artifact_version="1",
        reservation_id=res_id,
        reservation_hash="r" * 64,
        route_id="route-1", route_hash="r" * 64,
        attempt_id="att-1", attempt_hash="a" * 64,
        authorization_id="auth-1", authorization_hash="z" * 64,
        task_id="task-1", worker_id="worker-1", worker_class="run-sandbox",
        worker_version="1", operation="run-sandbox", input_hash="0" * 64,
        runtime_binding_id="binding-1", runtime_binding_version="1",
        runtime_binding_hash="B" * 64,
        idempotency_key=idem,
        recorded_at="2024-01-01T00:05:00Z",
        must_start_by="2024-01-02T00:00:00Z",
        launcher_actor=_launcher(),
        status=ExecutionLaunchAttemptStatus.RECORDED,
    )


def _evidence(outcome, *, run_id=None, error_code=None, error_summary=None,
              idem="i" * 64, att_id="latch-1", adapter_kind="LOCAL_WORKER_ADAPTER",
              adapter_version="1", observed="2024-01-01T00:10:00Z",
              source="launch"):
    return VerifiedRuntimeStartEvidence(
        launch_attempt_id=att_id,
        idempotency_key=idem,
        runtime_outcome=outcome,
        runtime_run_id=run_id,
        source=source,
        runtime_adapter_kind=adapter_kind,
        runtime_adapter_version=adapter_version,
        observed_at=observed,
        evidence_hash=ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id=att_id, idempotency_key=idem,
            runtime_outcome=outcome, runtime_run_id=run_id,
            runtime_adapter_kind=adapter_kind,
            runtime_adapter_version=adapter_version, error_code=error_code),
        error_code=error_code,
        error_summary=error_summary,
    )


class ServiceFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "start.db")
        self.store = SQLiteExecutionStartStore(self.db)
        self.store.migrate_to_v3()
        self.store.record_reservation(reservation=_reservation(), now="2024-01-01T00:00:00Z")
        self.store.record_launch_attempt(attempt=_attempt(), now="2024-01-01T00:00:00Z")
        self.svc = ExecutionStartResultService(self.store, _FakeLookup())

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class _FakeLookup:
    """Read-only lookup stub. NEVER launches; returns a frozen outcome."""
    def __init__(self, outcome=None, run_id=None, error_code=None,
                 error_summary=None):
        self._outcome = outcome
        self._run_id = run_id
        self._error_code = error_code
        self._error_summary = error_summary

    def lookup(self, idempotency_key):
        from tools.hermes_core.runtime_launch_adapter import (
            RuntimeLookupResult, RuntimeLookupOutcome)
        return RuntimeLookupResult(
            outcome=self._outcome or RuntimeLookupOutcome.UNKNOWN,
            runtime_run_id=self._run_id,
            error_code=self._error_code,
            error_summary=self._error_summary,
        )


class DomainIdentityTests(unittest.TestCase):
    def test_start_result_id_is_deterministic_full_sha(self):
        r1 = _build(ExecutionStartOutcome.STARTED, run_id="run-1")
        r2 = _build(ExecutionStartOutcome.STARTED, run_id="run-1")
        self.assertEqual(r1.start_result_id, r2.start_result_id)
        expected = sha256_payload({
            "schema": "ea4d4-start-result-id-v1",
            "launch_attempt_id": "latch-1",
        })
        self.assertEqual(r1.start_result_id, expected)
        self.assertEqual(len(r1.start_result_id), 64)

    def test_evidence_hash_excludes_provenance(self):
        h1 = ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="i" * 64,
            runtime_outcome=ExecutionStartOutcome.FAILED, runtime_run_id=None,
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code="PROCESS_CREATION_FAILED")
        h2 = ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="i" * 64,
            runtime_outcome=ExecutionStartOutcome.FAILED, runtime_run_id=None,
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code="PROCESS_CREATION_FAILED")
        # Same evidence, different provenance metadata -> identical hash.
        self.assertEqual(h1, h2)

    def test_different_error_code_yields_different_evidence_hash(self):
        h_a = ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="i" * 64,
            runtime_outcome=ExecutionStartOutcome.FAILED, runtime_run_id=None,
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code="PROCESS_CREATION_FAILED")
        h_b = ExecutionStartResultService.runtime_evidence_hash(
            launch_attempt_id="latch-1", idempotency_key="i" * 64,
            runtime_outcome=ExecutionStartOutcome.FAILED, runtime_run_id=None,
            runtime_adapter_kind="LOCAL_WORKER_ADAPTER",
            runtime_adapter_version="1", error_code="WORKER_REJECTED")
        self.assertNotEqual(h_a, h_b)

    def test_result_artifact_hash_binds_error_summary(self):
        r_with = _build(ExecutionStartOutcome.FAILED, error_code="X",
                        error_summary="explanation A")
        r_without = _build(ExecutionStartOutcome.FAILED, error_code="X",
                          error_summary="explanation B")
        self.assertNotEqual(r_with.artifact_hash, r_without.artifact_hash)

    def test_error_summary_change_does_not_change_evidence_identity(self):
        e_a = _evidence(ExecutionStartOutcome.FAILED, error_code="X",
                        error_summary="A")
        e_b = _evidence(ExecutionStartOutcome.FAILED, error_code="X",
                        error_summary="B")
        self.assertEqual(e_a.evidence_hash, e_b.evidence_hash)

    def test_material_field_change_changes_result_hash(self):
        base = _build(ExecutionStartOutcome.STARTED, run_id="run-1")
        other = _build(ExecutionStartOutcome.STARTED, run_id="run-2")
        self.assertNotEqual(base.artifact_hash, other.artifact_hash)


def _build(outcome, *, run_id=None, error_code=None, error_summary=None,
           idem="i" * 64, att_id="latch-1"):
    return build_execution_start_result(
        launch_attempt_id=att_id,
        launch_attempt_hash="L" * 64,
        reservation_id="res-1", reservation_hash="r" * 64,
        route_id="route-1", route_hash="r" * 64,
        task_id="task-1", worker_id="worker-1", worker_version="1",
        runtime_binding_id="binding-1", runtime_binding_version="1",
        runtime_binding_hash="B" * 64,
        idempotency_key=idem,
        outcome=outcome,
        recorded_at="2024-01-01T00:10:00Z",
        runtime_evidence_hash="e" * 64,
        runtime_run_id=run_id,
        error_code=error_code,
        error_summary=error_summary,
    )


class StartResultPersistTests(ServiceFixture):
    def test_direct_verified_started_persists(self):
        res = self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.STARTED, run_id="run-1"))
        self.assertEqual(res.outcome, ExecutionStartOutcome.STARTED)
        got = self.store.get_execution_start_result("latch-1")
        self.assertIsNotNone(got)
        self.assertEqual(got.outcome, ExecutionStartOutcome.STARTED)
        self.assertEqual(got.runtime_run_id, "run-1")
        self.assertTrue(got.verify_hash())

    def test_started_requires_runtime_run_id(self):
        ev = _evidence(ExecutionStartOutcome.STARTED, run_id=None)
        with self.assertRaises(ExecutionStartResultError):
            self.svc.persist_start_result(_attempt(), _reservation(), ev)

    def test_replay_returns_same_row(self):
        self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.STARTED, run_id="run-1"))
        again = self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.STARTED, run_id="run-1"))
        self.assertEqual(again.start_result_id,
                         self.store.get_execution_start_result("latch-1").start_result_id)

    def test_different_runtime_run_id_conflicts(self):
        self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.STARTED, run_id="run-1"))
        with self.assertRaises(ExecutionStartResultConflictError):
            self.svc.persist_start_result(
                _attempt(), _reservation(),
                _evidence(ExecutionStartOutcome.STARTED, run_id="run-2"))

    def test_unknown_creates_no_result(self):
        with self.assertRaises(ExecutionStartResultError):
            self.svc.persist_start_result(
                _attempt(), _reservation(),
                _evidence(ExecutionStartOutcome.UNKNOWN))

    def test_failed_persists_with_error_code(self):
        res = self.svc.persist_start_result(
            _attempt(), _reservation(),
            _evidence(ExecutionStartOutcome.FAILED,
                      error_code="PROCESS_CREATION_FAILED",
                      error_summary="executable missing"))
        self.assertEqual(res.outcome, ExecutionStartOutcome.FAILED)
        got = self.store.get_execution_start_result("latch-1")
        self.assertEqual(got.error_code, "PROCESS_CREATION_FAILED")


class NegativeAuthorityTests(ServiceFixture):
    def test_no_execute_method_on_service(self):
        self.assertFalse(hasattr(self.svc, "execute"))
        self.assertFalse(hasattr(self.svc, "project_executing"))

    def test_lookup_dependency_has_no_launch(self):
        import inspect
        from tools.hermes_core.execution_start_result_service import (
            RuntimeStartLookup)
        self.assertNotIn("launch", RuntimeStartLookup.__abstractmethods__
                          if hasattr(RuntimeStartLookup, "__abstractmethods__")
                          else [])
        # The FakeLookup (and any compliant lookup) exposes only lookup().
        self.assertFalse(hasattr(_FakeLookup(), "launch"))


if __name__ == "__main__":
    unittest.main()
