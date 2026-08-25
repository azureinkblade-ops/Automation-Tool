"""
Tests for chapter_workflow.py — durable state machine for chapter production.

Run: python -m pytest tests/test_chapter_workflow.py -v
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from chapter_workflow import (
    ChapterWorkflowController,
    Collaborators,
    State,
    WorkflowState,
    WorkflowStore,
)


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def store(tmp_db):
    return WorkflowStore(tmp_db)


@pytest.fixture
def collab():
    return Collaborators()


@pytest.fixture
def ctrl(store, collab):
    return ChapterWorkflowController(store, collab)


# ─── State transitions ────────────────────────────────────────────

class TestTransitions:
    def test_can_transition_valid(self):
        ws = WorkflowState(workflow_id="HA-87", novel="HA", chapter_number=87)
        assert ws.can_transition_to(State.CONTEXT_LOADED)
        assert not ws.can_transition_to(State.DONE)

    def test_init_to_context_loaded(self, ctrl, store):
        ws = ctrl.create("HA", 87)
        ctrl._transition(ws, State.CONTEXT_LOADED)
        assert ws.state == State.CONTEXT_LOADED
        loaded = store.load("HA-87")
        assert loaded.state == State.CONTEXT_LOADED

    def test_illegal_transition_raises(self, ctrl):
        ws = ctrl.create("HA", 87)
        with pytest.raises(ValueError, match="Invalid transition"):
            ctrl._transition(ws, State.DONE)

    def test_terminal_states(self, ctrl, store):
        ws = ctrl.create("HA", 87)
        ws.state = State.DONE
        store.save(ws)
        assert not ws.can_transition_to(State.WRITING)


# ─── Persistence ──────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_load(self, store):
        ws = WorkflowState(workflow_id="EN-120", novel="EN", chapter_number=120)
        ws.artifacts["context"] = "test"
        store.save(ws)
        loaded = store.load("EN-120")
        assert loaded.novel == "EN"
        assert loaded.chapter_number == 120
        assert loaded.artifacts["context"] == "test"

    def test_survives_restart(self, tmp_db):
        """Simulate process restart: new store instance reads old data."""
        store1 = WorkflowStore(tmp_db)
        ws = WorkflowState(workflow_id="SF-50", novel="SF", chapter_number=50,
                           state=State.BRIEF_DRAFTED)
        store1.save(ws)

        # New process
        store2 = WorkflowStore(tmp_db)
        loaded = store2.load("SF-50")
        assert loaded.state == State.BRIEF_DRAFTED

    def test_list_active(self, store):
        ws1 = WorkflowState(workflow_id="A", novel="HA", chapter_number=1, state=State.WRITING)
        ws2 = WorkflowState(workflow_id="B", novel="EN", chapter_number=2, state=State.DONE)
        store.save(ws1)
        store.save(ws2)
        active = store.list_active()
        assert len(active) == 1
        assert active[0].workflow_id == "A"


# ─── Idempotency ──────────────────────────────────────────────────

class TestIdempotency:
    def test_run_twice_no_duplicate(self, ctrl, collab, store):
        """Running a stage twice should not duplicate artifacts."""
        calls = {"count": 0}

        def fake_write(novel, chapter, brief):
            calls["count"] += 1
            return f"draft-{calls['count']}"

        collab.write_chapter = fake_write
        ws = ctrl.create("HA", 87)
        ws.state = State.BRIEF_APPROVED
        ws.artifacts["brief"] = "test-brief"
        store.save(ws)

        ctrl.run_writing(ws)
        ctrl.run_writing(ws)  # second call
        assert calls["count"] == 1  # not called again


# ─── Revision loop ────────────────────────────────────────────────

class TestRevisionLoop:
    def test_review_fail_returns_to_writing(self, ctrl, store, collab):
        collab.review_continuity = lambda *a, **k: {"pass": False, "issues": ["test"]}
        ws = ctrl.create("HA", 87)
        ws.state = State.WRITING
        ws.artifacts["draft"] = "test-draft"
        store.save(ws)

        ctrl.run_reviewing(ws)
        # From WRITING: review fail = revise loop, stay in WRITING, increment attempt
        assert ws.state == State.WRITING
        assert ws.attempt == 2

    def test_validation_fail_returns_to_writing(self, ctrl, store, collab):
        collab.validate_chapter = lambda *a, **k: {"valid": False, "errors": ["test"]}
        ws = ctrl.create("HA", 87)
        ws.state = State.REVIEWING
        ws.artifacts["draft"] = "test-draft"
        store.save(ws)

        ctrl.run_validating(ws)
        assert ws.state == State.WRITING


# ─── Approval gate ────────────────────────────────────────────────

class TestApprovalGate:
    def test_blocked_waits_for_approval(self, ctrl, store):
        ws = ctrl.create("HA", 87)
        ws.state = State.BRIEF_DRAFTED
        store.save(ws)

        ctrl._wait_for_approval(ws)
        assert ws.state == State.BLOCKED

    def test_unblock_approves(self, ctrl, store):
        ws = ctrl.create("HA", 87)
        ws.state = State.BLOCKED
        store.save(ws)

        ctrl.unblock(ws)
        assert ws.state == State.BRIEF_APPROVED
        assert ws.approved


# ─── Serialization ────────────────────────────────────────────────

class TestSerialization:
    def test_to_from_dict(self):
        ws = WorkflowState(
            workflow_id="HP-100", novel="HP", chapter_number=100,
            state=State.WRITING, attempt=2,
            artifacts={"context": "x", "brief": "y"},
        )
        d = ws.to_dict()
        ws2 = WorkflowState.from_dict(d)
        assert ws2.workflow_id == ws.workflow_id
        assert ws2.state == ws.state
        assert ws2.attempt == 2
        assert ws2.artifacts["context"] == "x"


# ─── Error handling ───────────────────────────────────────────────

class TestErrorHandling:
    def test_collaborator_error_fails_workflow(self, ctrl, collab, store):
        collab.fetch_latest_chapter = lambda *a, **k: (_ for _ in []).throw(
            RuntimeError("network down")
        ) or (_ for _ in ()).throw(RuntimeError("network down"))
        ws = ctrl.create("HA", 87)
        ctrl.run_context_loaded(ws)
        assert ws.state == State.FAILED
        assert "network down" in ws.last_error

    def test_missing_brief_fails(self, ctrl, store):
        ws = ctrl.create("HA", 87)
        ws.state = State.BRIEF_APPROVED
        ws.artifacts["brief"] = None
        store.save(ws)
        ctrl.run_writing(ws)
        assert ws.state == State.FAILED


# ─── Concurrency (basic) ──────────────────────────────────────────

class TestConcurrency:
    def test_store_thread_safety(self, store):
        """Multiple threads saving concurrently should not corrupt data."""
        import threading
        errors = []
        def save_many(n):
            try:
                for i in range(10):
                    ws = WorkflowState(
                        workflow_id=f"W-{n}-{i}", novel="HA", chapter_number=i,
                    )
                    store.save(ws)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=save_many, args=(n,)) for n in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors
