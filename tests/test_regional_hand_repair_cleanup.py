"""Tests for EA-4D.4F Regional Hand Repair cleanup ownership."""

import os
import tempfile
import pytest

from tools.regional_hand_repair_evidence import (
    RegionalHandRepairEvidenceStore,
)
from tools.regional_hand_repair_cleanup import (
    CleanupResult,
    CleanupPreconditionsNotMetError,
    CleanupRecordError,
    RegionalHandRepairCleanupOrchestrator,
)


@pytest.fixture
def store():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_evidence.db")
    store = RegionalHandRepairEvidenceStore(db_path)
    yield store
    store.close()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def orchestrator(store):
    return RegionalHandRepairCleanupOrchestrator(store)


class TestCheckPreconditions:
    def test_nonexistent_run(self, orchestrator):
        met, unmet = orchestrator.check_preconditions("nonexistent")
        assert not met
        assert len(unmet) > 0

    def test_recorded_state_not_met(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        met, unmet = orchestrator.check_preconditions("latch-1")
        assert not met
        assert any("not in terminal state" in u for u in unmet)

    def test_verified_state_met(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        store.transition_state("latch-1", "SUBMITTING")
        store.transition_state("latch-1", "STARTED", runtime_run_id="run-1")
        store.transition_state("latch-1", "OUTPUT_CAPTURED", result_json="{}", result_sha256="b" * 64)
        store.transition_state("latch-1", "VERIFIED")
        met, unmet = orchestrator.check_preconditions("latch-1")
        assert met

    def test_verified_without_result_not_met(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        store.transition_state("latch-1", "SUBMITTING")
        store.transition_state("latch-1", "STARTED", runtime_run_id="run-1")
        store.transition_state("latch-1", "OUTPUT_CAPTURED")  # No result
        store.transition_state("latch-1", "VERIFIED")
        met, unmet = orchestrator.check_preconditions("latch-1")
        assert not met
        assert any("no result_json" in u for u in unmet)


class TestRecordCleanup:
    def test_record_eligible(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        orchestrator.record_cleanup_eligible("latch-1")
        assert orchestrator.is_cleanup_eligible("latch-1")

    def test_record_complete(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        orchestrator.record_cleanup_complete(
            "latch-1",
            models_unloaded=True,
            memory_freed=True,
            comfyui_reachable=True,
        )
        assert orchestrator.is_cleanup_complete("latch-1")

    def test_record_failure(self, orchestrator, store):
        store.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        orchestrator.record_cleanup_failure("latch-1", "test error")
        events = store.get_events("latch-1")
        failure_events = [e for e in events if e.event_type == "CLEANUP_FAILURE"]
        assert len(failure_events) == 1
