"""
Tests for chapter_workflow_api.py — semantic API routes.
"""

import json
import tempfile
from pathlib import Path

import pytest

from chapter_workflow import Collaborators, State, WorkflowStore, ChapterWorkflowController
from chapter_workflow_api import ChapterWorkflowAPI


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink(missing_ok=True)


@pytest.fixture
def api(tmp_db):
    store = WorkflowStore(tmp_db)
    collab = Collaborators(
        fetch_latest_chapter=lambda n: {"latest_number": 86, "next_number": 87, "chapter_text": "test"},
        fetch_studio_bible=lambda n: {"protagonist": "Kai"},
        fetch_continuity=lambda n, c: {"snapshot": {}},
        generate_brief=lambda n, c, j: '{"title": "test"}',
        write_chapter=lambda n, c, b: f"Chapter {c} - Test\n\nThis is a test chapter.\n" + "word " * 3000,
        review_continuity=lambda n, c, d, j: {"pass": True, "issues": []},
        validate_chapter=lambda n, c, d: {"valid": True, "errors": []},
    )
    ctrl = ChapterWorkflowController(store, collab)
    output_root = Path(tempfile.mkdtemp())
    return ChapterWorkflowAPI(ctrl, output_root)


class TestStart:
    def test_start_creates_workflow(self, api):
        resp, code = api.start({"abbr": "HA", "chapter_number": 87})
        assert code == 201
        assert resp["workflow_id"] == "HA-87"
        assert resp["state"] == "context_loaded"

    def test_start_requires_abbr(self, api):
        resp, code = api.start({"chapter_number": 87})
        assert code == 400

    def test_start_requires_chapter(self, api):
        resp, code = api.start({"abbr": "HA"})
        assert code == 400

    def test_start_existing_returns_200(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        resp, code = api.start({"abbr": "HA", "chapter_number": 87})
        assert code == 200
        assert "already exists" in resp["message"]


class TestAdvance:
    def test_advance_runs_current_stage(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        resp, code = api.advance({"workflow_id": "HA-87"})
        assert code == 200
        assert resp["state"] == "brief_drafted"

    def test_advance_blocked_returns_message(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        api.advance({"workflow_id": "HA-87"})  # → brief_drafted
        api.advance({"workflow_id": "HA-87"})  # → blocked
        resp, code = api.advance({"workflow_id": "HA-87"})
        assert code == 200
        assert "blocked" in resp["message"].lower()

    def test_advance_done_returns_complete(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        api.advance({"workflow_id": "HA-87"})  # → brief_drafted
        api.advance({"workflow_id": "HA-87"})  # → blocked
        api.approve({"workflow_id": "HA-87"})  # → brief_approved
        api.advance({"workflow_id": "HA-87"})  # → writing
        api.advance({"workflow_id": "HA-87"})  # → reviewing
        api.advance({"workflow_id": "HA-87"})  # → validating
        api.advance({"workflow_id": "HA-87"})  # → done
        resp, code = api.advance({"workflow_id": "HA-87"})
        assert code == 200
        assert "complete" in resp["message"].lower()


class TestApprove:
    def test_approve_unblocks(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        api.advance({"workflow_id": "HA-87"})  # → brief_drafted
        api.advance({"workflow_id": "HA-87"})  # → blocked
        resp, code = api.approve({"workflow_id": "HA-87"})
        assert code == 200
        assert resp["state"] == "brief_approved"

    def test_approve_non_blocked_fails(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        resp, code = api.approve({"workflow_id": "HA-87"})
        assert code == 400


class TestStatus:
    def test_status_returns_full_state(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        resp, code = api.status("HA-87")
        assert code == 200
        assert resp["workflow_id"] == "HA-87"
        assert resp["state"] == "context_loaded"
        assert "artifacts" in resp
        assert "approval_required" in resp
        assert "approved" in resp


class TestListActive:
    def test_list_excludes_terminal(self, api):
        api.start({"abbr": "HA", "chapter_number": 87})
        api.start({"abbr": "EN", "chapter_number": 120})
        resp, code = api.list_active()
        assert code == 200
        assert resp["count"] == 2
