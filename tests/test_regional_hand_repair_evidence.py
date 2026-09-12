"""Tests for EA-4D.4F durable Regional Hand Repair pilot workload evidence."""

import os
import tempfile
import pytest

from tools.regional_hand_repair_evidence import (
    ALLOWED_STATES,
    TERMINAL_STATES,
    ALLOWED_TRANSITIONS,
    DuplicateRequestError,
    InvalidStateTransitionError,
    RecordNotFoundError,
    RegionalHandRepairEvidenceStore,
)


@pytest.fixture
def store():
    """Create a temporary evidence store."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_evidence.db")
        store = RegionalHandRepairEvidenceStore(db_path)
        yield store
        store.close()


class TestAllowedStates:
    def test_all_defined_states_are_allowed(self):
        for state in ALLOWED_TRANSITIONS:
            assert state in ALLOWED_STATES

    def test_terminal_states_have_no_transitions(self):
        for state in TERMINAL_STATES:
            assert len(ALLOWED_TRANSITIONS.get(state, set())) == 0

    def test_verified_is_terminal(self):
        assert "VERIFIED" in TERMINAL_STATES

    def test_failed_is_terminal(self):
        assert "FAILED" in TERMINAL_STATES


class TestCreateRepairRun:
    def test_create_basic_run(self, store):
        run = store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        assert run.state == "RECORDED"
        assert run.launch_attempt_id == "latches-1"
        assert run.idempotency_key == "key-1"

    def test_create_duplicate_idempotency_fails(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        with pytest.raises(DuplicateRequestError):
            store.create_repair_run(
                launch_attempt_id="latches-2",
                idempotency_key="key-1",
                repair_execution_id="rex-2",
                task_input_sha256="b" * 64,
                worker_id="regional-hand-repair-worker",
                worker_version="1.0",
                runtime_binding_id="bind-2",
            )


class TestGetRepairRun:
    def test_get_existing(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        run = store.get_repair_run("latches-1")
        assert run is not None
        assert run.launch_attempt_id == "latches-1"

    def test_get_nonexistent(self, store):
        assert store.get_repair_run("nonexistent") is None

    def test_get_by_idempotency(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        run = store.get_repair_run_by_idempotency("key-1")
        assert run is not None
        assert run.launch_attempt_id == "latches-1"


class TestStateTransitions:
    def test_recorded_to_submitting(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        run = store.transition_state("latches-1", "SUBMITTING")
        assert run.state == "SUBMITTING"

    def test_invalid_transition_fails(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        with pytest.raises(InvalidStateTransitionError):
            store.transition_state("latches-1", "VERIFIED")

    def test_terminal_state_cannot_transition(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        store.transition_state("latches-1", "FAILED")
        with pytest.raises(InvalidStateTransitionError):
            store.transition_state("latches-1", "STARTED")


class TestEventChain:
    def test_append_event(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        event = store.append_event("latches-1", "SUBMIT", '{"prompt_id": "abc"}')
        assert event.sequence_no == 1
        assert event.previous_event_sha256 is None

    def test_event_chain_integrity(self, store):
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        store.append_event("latches-1", "SUBMIT", '{"prompt_id": "abc"}')
        store.append_event("latches-1", "STARTED", '{"run_id": "xyz"}')
        store.append_event("latches-1", "OUTPUT", '{"file": "out.png"}')

        assert store.verify_event_chain("latches-1")

        events = store.get_events("latches-1")
        assert len(events) == 3
        assert events[0].sequence_no == 1
        assert events[1].sequence_no == 2
        assert events[2].sequence_no == 3


class TestIdempotency:
    def test_same_idempotency_same_result(self, store):
        """Same idempotency key should return same result on replay."""
        store.create_repair_run(
            launch_attempt_id="latches-1",
            idempotency_key="key-1",
            repair_execution_id="rex-1",
            task_input_sha256="a" * 64,
            worker_id="regional-hand-repair-worker",
            worker_version="1.0",
            runtime_binding_id="bind-1",
        )
        store.transition_state("latches-1", "FAILED")

        # Replay with same key should fail (duplicate)
        with pytest.raises(DuplicateRequestError):
            store.create_repair_run(
                launch_attempt_id="latches-2",
                idempotency_key="key-1",
                repair_execution_id="rex-2",
                task_input_sha256="a" * 64,
                worker_id="regional-hand-repair-worker",
                worker_version="1.0",
                runtime_binding_id="bind-2",
            )
