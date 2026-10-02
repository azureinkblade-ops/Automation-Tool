"""EA-4D.4F recovery-boundary contract and workload replay proofs."""

from __future__ import annotations

import json

import pytest

from tools.regional_hand_repair_adapter import (
    FakeComfyUITransport,
    RegionalHandRepairComfyUIAdapter,
)
from tools.regional_hand_repair_cleanup import (
    RegionalHandRepairCleanupOrchestrator,
)
from tools.regional_hand_repair_evidence import (
    RegionalHandRepairEvidenceStore,
)
from tools.regional_hand_repair_submission import (
    DuplicateSubmissionError,
    RegionalHandRepairSubmissionOrchestrator,
    UncertainSubmissionError,
)
from tools.regional_hand_repair_workflow import build_frozen_template


RECOVERY_MATRIX = (
    (1, "approval recorded -> crash before authorization", "authority issuance replay"),
    (2, "authorization -> crash before attempt", "authorization claim replay"),
    (3, "attempt -> crash before routing", "route replay"),
    (4, "route -> crash before LaunchAttempt", "reservation/admission replay"),
    (5, "LaunchAttempt -> crash before handoff", "launch coordinator recovery"),
    (6, "root receives launch ID -> crash before 4E", "4E E1 recovery"),
    (7, "submit intent persisted -> crash before request", "SUBMITTING blocks replay"),
    (8, "request accepted -> response lost", "SUBMISSION_UNKNOWN blocks replay"),
    (9, "STARTED persisted -> crash before projection", "4E E2 recovery"),
    (10, "projection committed -> acknowledgement lost", "4E E3 recovery"),
    (11, "output captured -> crash before validation", "OUTPUT_CAPTURED replay"),
    (12, "validation complete -> crash before cleanup", "VERIFIED replay"),
    (13, "cleanup request state -> acknowledgement lost", "cleanup event replay"),
    (14, "duplicate explicit manual submission", "idempotency-key replay"),
)


def _new_store(tmp_path, name: str) -> RegionalHandRepairEvidenceStore:
    return RegionalHandRepairEvidenceStore(tmp_path / f"{name}.db")


def _create_run(store: RegionalHandRepairEvidenceStore, *, state: str) -> None:
    store.create_repair_run(
        launch_attempt_id="latch-1",
        idempotency_key="key-1",
        repair_execution_id="rex-1",
        task_input_sha256="a" * 64,
        worker_id="regional-hand-repair-worker",
        worker_version="1.0",
        runtime_binding_id="bind-1",
    )
    if state == "RECORDED":
        return
    store.transition_state("latch-1", "SUBMITTING")
    if state == "SUBMITTING":
        return
    if state == "SUBMISSION_UNKNOWN":
        store.transition_state("latch-1", state)
        return
    store.transition_state("latch-1", "STARTED", runtime_run_id="prompt-1")
    if state == "STARTED":
        return
    result = json.dumps({
        "prompt_id": "prompt-1",
        "filename": "repair.png",
        "subfolder": "",
        "type": "output",
    })
    store.transition_state(
        "latch-1", "OUTPUT_CAPTURED", result_json=result,
        result_sha256="b" * 64,
    )
    if state == "OUTPUT_CAPTURED":
        return
    store.transition_state("latch-1", "VERIFIED")


def _submit(orchestrator: RegionalHandRepairSubmissionOrchestrator):
    return orchestrator.submit(
        launch_attempt_id="latch-1",
        idempotency_key="key-1",
        repair_execution_id="rex-1",
        task_input_sha256="a" * 64,
        worker_id="regional-hand-repair-worker",
        worker_version="1.0",
        runtime_binding_id="bind-1",
        workflow=build_frozen_template(),
    )


def test_recovery_matrix_is_exact_complete_and_ordered():
    assert tuple(row[0] for row in RECOVERY_MATRIX) == tuple(range(1, 15))
    assert len({row[1] for row in RECOVERY_MATRIX}) == 14
    assert all(row[2] for row in RECOVERY_MATRIX)


@pytest.mark.parametrize(
    ("state", "error_type"),
    (("SUBMITTING", DuplicateSubmissionError),
     ("SUBMISSION_UNKNOWN", UncertainSubmissionError)),
)
def test_boundaries_7_and_8_never_resubmit(tmp_path, state, error_type):
    store = _new_store(tmp_path, state.lower())
    transport = FakeComfyUITransport()
    try:
        _create_run(store, state=state)
        orchestrator = RegionalHandRepairSubmissionOrchestrator(
            store, RegionalHandRepairComfyUIAdapter(transport=transport)
        )
        with pytest.raises(error_type):
            _submit(orchestrator)
        assert transport.submissions == []
        assert store.get_repair_run("latch-1").launch_attempt_id == "latch-1"
    finally:
        store.close()


@pytest.mark.parametrize("state", ("STARTED", "OUTPUT_CAPTURED", "VERIFIED"))
def test_boundaries_9_11_12_replay_identity_without_resubmission(tmp_path, state):
    store = _new_store(tmp_path, state.lower())
    transport = FakeComfyUITransport()
    try:
        _create_run(store, state=state)
        orchestrator = RegionalHandRepairSubmissionOrchestrator(
            store, RegionalHandRepairComfyUIAdapter(transport=transport)
        )
        result = _submit(orchestrator)
        assert result.prompt_id == "prompt-1"
        assert transport.submissions == []
        assert store.get_repair_run("latch-1").launch_attempt_id == "latch-1"
    finally:
        store.close()


def test_boundary_13_cleanup_ack_loss_is_idempotent(tmp_path):
    store = _new_store(tmp_path, "cleanup")
    try:
        _create_run(store, state="VERIFIED")
        cleanup = RegionalHandRepairCleanupOrchestrator(store)
        cleanup.record_cleanup_eligible("latch-1")
        cleanup.record_cleanup_eligible("latch-1")
        cleanup.record_cleanup_complete(
            "latch-1", models_unloaded=True, memory_freed=True,
            comfyui_reachable=True,
        )
        cleanup.record_cleanup_complete(
            "latch-1", models_unloaded=True, memory_freed=True,
            comfyui_reachable=True,
        )
        event_types = [event.event_type for event in store.get_events("latch-1")]
        assert event_types.count("CLEANUP_ELIGIBLE") == 1
        assert event_types.count("CLEANUP_COMPLETE") == 1
    finally:
        store.close()


def test_boundary_14_duplicate_manual_submission_has_one_runtime_request(tmp_path):
    store = _new_store(tmp_path, "manual-duplicate")
    transport = FakeComfyUITransport()
    try:
        orchestrator = RegionalHandRepairSubmissionOrchestrator(
            store, RegionalHandRepairComfyUIAdapter(transport=transport)
        )
        first = _submit(orchestrator)
        second = _submit(orchestrator)
        assert first.prompt_id == second.prompt_id
        assert len(transport.submissions) == 1
        assert store.get_repair_run("latch-1").launch_attempt_id == "latch-1"
    finally:
        store.close()
