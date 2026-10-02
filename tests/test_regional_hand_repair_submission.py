"""Tests for EA-4D.4F crash-safe Regional Hand Repair submission orchestrator."""

import os
import tempfile
import pytest

from tools.regional_hand_repair_evidence import (
    RegionalHandRepairEvidenceStore,
)
from tools.regional_hand_repair_adapter import (
    RegionalHandRepairComfyUIAdapter,
    FakeComfyUITransport,
)
from tools.regional_hand_repair_submission import (
    RegionalHandRepairSubmissionOrchestrator,
    SubmissionResult,
    SubmissionError,
    WorkflowRejectedError,
    TransportUnavailableError,
    UncertainSubmissionError,
    DuplicateSubmissionError,
    create_submission_orchestrator,
)
from tools.regional_hand_repair_workflow import build_frozen_template


@pytest.fixture
def fake_transport():
    return FakeComfyUITransport()


@pytest.fixture
def orchestrator(fake_transport):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_evidence.db")
    evidence_store = RegionalHandRepairEvidenceStore(db_path)
    adapter = RegionalHandRepairComfyUIAdapter(transport=fake_transport)
    orchestrator = RegionalHandRepairSubmissionOrchestrator(evidence_store, adapter)
    yield orchestrator
    evidence_store.close()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestSubmit:
    def test_submit_valid_workflow(self, orchestrator, fake_transport):
        workflow = build_frozen_template()
        result = orchestrator.submit(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
            workflow=workflow,
        )
        assert isinstance(result, SubmissionResult)
        assert result.prompt_id.startswith("fake-prompt-")
        assert len(fake_transport.submissions) == 1

    def test_submit_invalid_workflow_raises(self, orchestrator, fake_transport):
        workflow = build_frozen_template()
        workflow["nodes"]["X1"] = {"class_type": "CustomNode", "inputs": {}}
        with pytest.raises(WorkflowRejectedError):
            orchestrator.submit(
                launch_attempt_id="latch-1",
                idempotency_key="key-1",
                repair_execution_id="rex-1",
                task_input_sha256="a" * 64,
                worker_id="regional-hand-repair-worker",
                worker_version="1.0",
                runtime_binding_id="bind-1",
                workflow=workflow,
            )
        assert len(fake_transport.submissions) == 0

    def test_submit_without_transport_raises(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test_evidence.db")
            evidence_store = RegionalHandRepairEvidenceStore(db_path)
            adapter = RegionalHandRepairComfyUIAdapter()  # No transport
            orchestrator = RegionalHandRepairSubmissionOrchestrator(evidence_store, adapter)

            workflow = build_frozen_template()
            with pytest.raises(TransportUnavailableError):
                orchestrator.submit(
                    launch_attempt_id="latch-1",
                    idempotency_key="key-1",
                    repair_execution_id="rex-1",
                    task_input_sha256="a" * 64,
                    worker_id="regional-hand-repair-worker",
                    worker_version="1.0",
                    runtime_binding_id="bind-1",
                    workflow=workflow,
                )
            evidence_store.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestReplayExisting:
    def test_replay_started_returns_result(self, orchestrator, fake_transport):
        """Replaying a STARTED record should return existing result without resubmission."""
        workflow = build_frozen_template()
        # First submission
        result1 = orchestrator.submit(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
            workflow=workflow,
        )
        # Record the result
        import json
        result_json = json.dumps({
            "prompt_id": result1.prompt_id,
            "filename": result1.filename,
            "subfolder": result1.subfolder,
            "type": result1.type,
        })
        orchestrator._evidence.transition_state(
            "latch-1", "OUTPUT_CAPTURED", result_json=result_json
        )
        orchestrator._evidence.transition_state("latch-1", "VERIFIED")

        # Second submission with same key should replay
        result2 = orchestrator.submit(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
            workflow=workflow,
        )
        assert result1.prompt_id == result2.prompt_id
        assert len(fake_transport.submissions) == 1  # Only one actual submission

    def test_replay_failed_raises(self, orchestrator, fake_transport):
        """Replaying a FAILED record should raise DuplicateSubmissionError."""
        workflow = build_frozen_template()
        # First submission
        orchestrator.submit(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
            workflow=workflow,
        )
        # Manually set state to FAILED
        orchestrator._evidence.transition_state("latch-1", "FAILED")

        # Second submission with same key should raise
        with pytest.raises(DuplicateSubmissionError):
            orchestrator.submit(
                launch_attempt_id="latch-1",
                idempotency_key="key-1",
                repair_execution_id="rex-1",
                task_input_sha256="a" * 64,
                worker_id="regional-hand-repair-worker",
                worker_version="1.0",
                runtime_binding_id="bind-1",
                workflow=workflow,
            )

    def test_replay_uncertain_raises(self, orchestrator, fake_transport):
        """Replaying an uncertain record should raise UncertainSubmissionError."""
        workflow = build_frozen_template()
        # Create record manually in SUBMISSION_UNKNOWN state
        orchestrator._evidence.create_repair_run(
            launch_attempt_id="latch-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        orchestrator._evidence.transition_state("latch-1", "SUBMITTING")
        orchestrator._evidence.transition_state("latch-1", "SUBMISSION_UNKNOWN")

        # Second submission with same key should raise
        with pytest.raises(UncertainSubmissionError):
            orchestrator.submit(
                launch_attempt_id="latch-1",
                idempotency_key="key-1",
                repair_execution_id="rex-1",
                task_input_sha256="a" * 64,
                worker_id="regional-hand-repair-worker",
                worker_version="1.0",
                runtime_binding_id="bind-1",
                workflow=workflow,
            )


class TestFactory:
    def test_create_submission_orchestrator(self, fake_transport):
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "test_evidence.db")
            orch = create_submission_orchestrator(db_path, transport=fake_transport)
            assert orch is not None
            assert orch._evidence is not None
            assert orch._adapter is not None
            orch._evidence.close()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
