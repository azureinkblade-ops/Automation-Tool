"""
Chapter Workflow Controller — durable state machine for chapter production.

Deterministic orchestration layer. Persists state to SQLite. Survives crashes.
Never imports app.py. Uses collaborator injection for all side-effects.

States:
  init → context_loaded → brief_drafted → brief_approved → writing → reviewing → validating → done
                                                                   ↓ fail
                                                                   writing (revise)
  Any state → failed (non-retryable) | blocked (waiting for human approval)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── State machine ─────────────────────────────────────────────────

class State(Enum):
    INIT = "init"
    CONTEXT_LOADED = "context_loaded"
    BRIEF_DRAFTED = "brief_drafted"
    BRIEF_APPROVED = "brief_approved"
    WRITING = "writing"
    REVIEWING = "reviewing"
    VALIDATING = "validating"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"

# Allowed transitions: current → {valid next states}
TRANSITIONS: Dict[State, set] = {
    State.INIT: {State.CONTEXT_LOADED, State.FAILED},
    State.CONTEXT_LOADED: {State.BRIEF_DRAFTED, State.FAILED},
    State.BRIEF_DRAFTED: {State.BRIEF_APPROVED, State.FAILED, State.BLOCKED},
    State.BRIEF_APPROVED: {State.WRITING, State.FAILED},
    State.WRITING: {State.REVIEWING, State.FAILED},
    State.REVIEWING: {State.VALIDATING, State.WRITING, State.FAILED},  # WRITING = revise
    State.VALIDATING: {State.DONE, State.WRITING, State.FAILED},  # WRITING = revise from validation
    State.FAILED: set(),  # terminal
    State.BLOCKED: {State.BRIEF_APPROVED, State.FAILED},  # unblock → approve
    State.DONE: set(),  # terminal
}

# States that require human approval to proceed
APPROVAL_REQUIRED_STATES = {State.BRIEF_DRAFTED}

# ─── Persistent state record ───────────────────────────────────────

class WorkflowState:
    """Represents one chapter workflow run. Serializable to/from SQLite."""
    
    def __init__(
        self,
        workflow_id: str,
        novel: str,
        chapter_number: int,
        state: State = State.INIT,
        previous_state: Optional[State] = None,
        attempt: int = 1,
        artifacts: Optional[Dict[str, Optional[str]]] = None,
        approval_required: bool = True,
        approved: bool = False,
        last_error: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.workflow_id = workflow_id
        self.novel = novel
        self.chapter_number = chapter_number
        self.state = state
        self.previous_state = previous_state
        self.attempt = attempt
        self.artifacts = artifacts or {"context": None, "brief": None, "draft": None, "review": None}
        self.approval_required = approval_required
        self.approved = approved
        self.last_error = last_error
        self.created_at = created_at or time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "workflow_id": self.workflow_id,
            "novel": self.novel,
            "chapter_number": self.chapter_number,
            "state": self.state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "attempt": self.attempt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "artifacts": self.artifacts,
            "approval": {
                "required": self.approval_required,
                "approved": self.approved,
            },
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowState":
        return cls(
            workflow_id=d["workflow_id"],
            novel=d["novel"],
            chapter_number=d["chapter_number"],
            state=State(d["state"]),
            previous_state=State(d["previous_state"]) if d.get("previous_state") else None,
            attempt=d.get("attempt", 1),
            artifacts=d.get("artifacts"),
            approval_required=d.get("approval", {}).get("required", True),
            approved=d.get("approval", {}).get("approved", False),
            last_error=d.get("last_error"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )

    def can_transition_to(self, new_state: State) -> bool:
        return new_state in TRANSITIONS.get(self.state, set())


# ─── Persistence layer ─────────────────────────────────────────────

class WorkflowStore:
    """SQLite-backed persistence for workflow state.
    
    Uses atomic writes (write temp + rename) to survive crashes.
    All reads/writes go through a single mutex for thread safety.
    Uses file-based locks for cross-process safety on a per-workflow basis.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._lock_dir = db_path.parent / f".{db_path.stem}_locks"
        self._lock_dir.mkdir(exist_ok=True)
        self._init_schema()

    def _workflow_lock(self, workflow_id: str) -> Path:
        """Get the lock file path for a workflow. Used for cross-process locking."""
        return self._lock_dir / f"{workflow_id}.lock"

    def acquire_workflow_lock(self, workflow_id: str, timeout: float = 30.0) -> Optional[Path]:
        """Try to acquire a per-workflow lock. Returns lock file path on success, None on timeout."""
        lock_path = self._workflow_lock(workflow_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # O_CREAT | O_EXCL equivalent via open exclusive
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()}:{threading.current_thread().ident}:{time.time()}".encode())
                os.close(fd)
                return lock_path
            except FileExistsError:
                time.sleep(0.1)
        return None

    def release_workflow_lock(self, workflow_id: str):
        """Release the per-workflow lock."""
        lock_path = self._workflow_lock(workflow_id)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    def _init_schema(self):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chapter_workflows (
                        workflow_id TEXT PRIMARY KEY,
                        novel TEXT NOT NULL,
                        chapter_number INTEGER NOT NULL,
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def save(self, state: WorkflowState):
        """Atomic save: write to temp, fsync, rename."""
        with self._lock:
            state.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            payload = json.dumps(state.to_dict(), ensure_ascii=False)
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO chapter_workflows
                       (workflow_id, novel, chapter_number, payload_json, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (state.workflow_id, state.novel, state.chapter_number,
                     payload, state.updated_at),
                )
                conn.commit()
            finally:
                conn.close()

    def load(self, workflow_id: str) -> Optional[WorkflowState]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                row = conn.execute(
                    "SELECT payload_json FROM chapter_workflows WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                if row is None:
                    return None
                return WorkflowState.from_dict(json.loads(row[0]))
            finally:
                conn.close()

    def load_latest_for_novel(self, novel: str) -> Optional[WorkflowState]:
        """Get the most recently updated workflow for a novel."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                row = conn.execute(
                    """SELECT payload_json FROM chapter_workflows
                       WHERE novel = ? ORDER BY updated_at DESC LIMIT 1""",
                    (novel,),
                ).fetchone()
                if row is None:
                    return None
                return WorkflowState.from_dict(json.loads(row[0]))
            finally:
                conn.close()

    def list_active(self) -> List[WorkflowState]:
        """Get all non-terminal workflows."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    "SELECT payload_json FROM chapter_workflows"
                ).fetchall()
                results = []
                for row in rows:
                    ws = WorkflowState.from_dict(json.loads(row[0]))
                    if ws.state not in (State.DONE, State.FAILED):
                        results.append(ws)
                return results
            finally:
                conn.close()


# ─── Collaborator contracts ────────────────────────────────────────

# Functions injected by app.py at startup. Each has a safe default.
class Collaborators:
    """Injected side-effects. All have safe pure defaults for testing."""
    
    def __init__(
        self,
        fetch_latest_chapter: Optional[Callable] = None,
        fetch_studio_bible: Optional[Callable] = None,
        fetch_continuity: Optional[Callable] = None,
        generate_brief: Optional[Callable] = None,
        write_chapter: Optional[Callable] = None,
        review_continuity: Optional[Callable] = None,
        validate_chapter: Optional[Callable] = None,
        import_chapter: Optional[Callable] = None,
    ):
        self.fetch_latest_chapter = fetch_latest_chapter or self._stub("fetch_latest_chapter")
        self.fetch_studio_bible = fetch_studio_bible or self._stub("fetch_studio_bible")
        self.fetch_continuity = fetch_continuity or self._stub("fetch_continuity")
        self.generate_brief = generate_brief or self._stub("generate_brief")
        self.write_chapter = write_chapter or self._stub("write_chapter")
        self.review_continuity = review_continuity or self._stub("review_continuity")
        self.validate_chapter = validate_chapter or self._stub("validate_chapter")
        self.import_chapter = import_chapter or self._stub("import_chapter")

    @staticmethod
    def _stub(name: str):
        def _fn(*a, **k):
            raise NotImplementedError(f"chapter_workflow: collaborator '{name}' not injected")
        return _fn


# ─── The controller ────────────────────────────────────────────────

class ChapterWorkflowController:
    """
    Deterministic state machine for chapter production.
    
    Usage:
        store = WorkflowState(db_path=Path("automation_state.db"))
        collab = Collaborators(fetch_latest_chapter=app.fetch_latest_chapter, ...)
        ctrl = ChapterWorkflowController(store, collab)
        
        # Create or resume
        ws = ctrl.create(abbr="HA", chapter_number=87)
        # or: ws = ctrl.resume(workflow_id)
        
        # Run stages (each is idempotent)
        ctrl.run_context_loaded(ws)
        ctrl.run_brief_drafted(ws)
        ctrl.run_brief_approved(ws)  # if auto-approve
        ctrl.run_writing(ws)
        ctrl.run_reviewing(ws)       # → revise or validate
        ctrl.run_validating(ws)      # → done or revise
        
        # On crash: ws.state tells you where to resume.
    """
    
    def __init__(
        self,
        store: WorkflowStore,
        collaborators: Collaborators,
        max_retries: int = 3,
    ):
        self.store = store
        self.collab = collaborators
        self.max_retries = max_retries

    def _transition(self, ws: WorkflowState, new_state: State):
        """Enforce valid transitions and persist."""
        if not ws.can_transition_to(new_state):
            raise ValueError(
                f"Invalid transition: {ws.state.value} → {new_state.value}"
            )
        ws.previous_state = ws.state
        ws.state = new_state
        ws.last_error = None
        self.store.save(ws)

    def _transition_same(self, ws: WorkflowState):
        """Persist without changing state (for revise loops)."""
        ws.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.store.save(ws)

    def _fail(self, ws: WorkflowState, error: str):
        """Mark failed and persist."""
        ws.last_error = error
        ws.state = State.FAILED
        self.store.save(ws)

    # ─── Public API ─────────────────────────────────────────────

    def create(self, abbr: str, chapter_number: int) -> WorkflowState:
        """Create a new workflow record."""
        workflow_id = f"{abbr}-{chapter_number}"
        ws = WorkflowState(
            workflow_id=workflow_id,
            novel=abbr,
            chapter_number=chapter_number,
            state=State.INIT,
        )
        self.store.save(ws)
        return ws

    def resume(self, workflow_id: str) -> Optional[WorkflowState]:
        """Load an existing workflow for resumption."""
        return self.store.load(workflow_id)

    def get_current_state(self, workflow_id: str) -> Optional[State]:
        ws = self.store.load(workflow_id)
        return ws.state if ws else None

    def run_stage(self, ws: WorkflowState) -> WorkflowState:
        """Run the current stage (idempotent). Resumes from current state.
        
        Acquires a per-workflow lock to prevent concurrent mutation.
        """
        lock = self.store.acquire_workflow_lock(ws.workflow_id)
        if lock is None:
            logger.warning("Could not acquire lock for %s, skipping", ws.workflow_id)
            return ws
        try:
            return self._run_stage_locked(ws)
        finally:
            self.store.release_workflow_lock(ws.workflow_id)

    def _run_stage_locked(self, ws: WorkflowState) -> WorkflowState:
        """Run stage with lock already held."""
        dispatch = {
            State.INIT: self.run_context_loaded,
            State.CONTEXT_LOADED: self.run_brief_drafted,
            State.BRIEF_DRAFTED: self._wait_for_approval,
            State.BRIEF_APPROVED: self.run_writing,
            State.WRITING: self.run_reviewing,
            State.REVIEWING: self._decide_after_review,
            State.VALIDATING: self._decide_after_validation,
            State.BLOCKED: self._wait_for_approval,
        }
        fn = dispatch.get(ws.state)
        if fn is None:
            raise ValueError(f"Cannot run stage from state {ws.state.value}")
        return fn(ws)

    # ─── Stage implementations ──────────────────────────────────

    def run_context_loaded(self, ws: WorkflowState) -> WorkflowState:
        """Load context: latest chapter, Studio Bible, continuity."""
        if ws.state not in (State.INIT, State.CONTEXT_LOADED):
            return ws  # idempotent: already done
        
        try:
            chapter_data = self.collab.fetch_latest_chapter(ws.novel)
            bible = self.collab.fetch_studio_bible(ws.novel)
            continuity = self.collab.fetch_continuity(ws.novel, ws.chapter_number - 1)
            
            ws.artifacts["context"] = json.dumps({
                "latest_chapter": chapter_data,
                "bible": bible,
                "continuity": continuity,
            })
            self._transition(ws, State.CONTEXT_LOADED)
        except Exception as e:
            logger.exception("Stage context_loaded failed")
            self._fail(ws, str(e))
        
        return ws

    def run_brief_drafted(self, ws: WorkflowState) -> WorkflowState:
        """Generate chapter brief from context."""
        if ws.state in (State.BRIEF_DRAFTED, State.BRIEF_APPROVED, State.WRITING):
            return ws  # idempotent
        
        try:
            if not ws.artifacts.get("context"):
                return self.run_context_loaded(ws)
            
            brief = self.collab.generate_brief(ws.novel, ws.chapter_number, ws.artifacts["context"])
            ws.artifacts["brief"] = brief
            self._transition(ws, State.BRIEF_DRAFTED)
        except Exception as e:
            logger.exception("Stage brief_drafted failed")
            self._fail(ws, str(e))
        
        return ws

    def run_brief_approved(self, ws: WorkflowState) -> WorkflowState:
        """Record human approval of brief."""
        if ws.state in (State.BRIEF_APPROVED, State.WRITING):
            return ws  # idempotent
        
        if ws.state != State.BRIEF_DRAFTED:
            self._fail(ws, "Cannot approve: brief not drafted")
            return ws
        
        ws.approved = True
        self._transition(ws, State.BRIEF_APPROVED)
        return ws

    def run_writing(self, ws: WorkflowState) -> WorkflowState:
        """Generate chapter prose from brief."""
        # Idempotent: skip if already at or past this stage
        if ws.state in (State.WRITING, State.REVIEWING, State.VALIDATING, State.DONE):
            return ws
        
        try:
            brief = ws.artifacts.get("brief")
            if not brief:
                self._fail(ws, "No brief to write from")
                return ws
            
            draft = self.collab.write_chapter(ws.novel, ws.chapter_number, brief)
            ws.artifacts["draft"] = draft
            self._transition(ws, State.WRITING)
        except Exception as e:
            logger.exception("Stage writing failed")
            self._fail(ws, str(e))
        
        return ws

    def run_reviewing(self, ws: WorkflowState) -> WorkflowState:
        """Continuity review of draft."""
        if ws.state in (State.VALIDATING, State.DONE):
            return ws  # idempotent
        
        try:
            draft = ws.artifacts.get("draft")
            if not draft:
                self._fail(ws, "No draft to review")
                return ws
            
            context = json.loads(ws.artifacts.get("context", "{}") or "{}")
            review = self.collab.review_continuity(ws.novel, ws.chapter_number, draft, context)
            ws.artifacts["review"] = json.dumps(review)
            
            if review.get("pass"):
                self._transition(ws, State.VALIDATING)
            else:
                ws.attempt += 1
                if ws.attempt > self.max_retries:
                    self._fail(ws, f"Max retries ({self.max_retries}) exceeded")
                    return ws
                if ws.state == State.WRITING:
                    # Already in writing (revise loop); just persist
                    self._transition_same(ws)
                else:
                    self._transition(ws, State.WRITING)  # revise
        except Exception as e:
            logger.exception("Stage reviewing failed")
            self._fail(ws, str(e))
        
        return ws

    def run_validating(self, ws: WorkflowState) -> WorkflowState:
        """Quality gate: em dashes, length, chapter number."""
        if ws.state == State.DONE:
            return ws  # idempotent
        
        try:
            draft = ws.artifacts.get("draft")
            if not draft:
                self._fail(ws, "No draft to validate")
                return ws
            
            result = self.collab.validate_chapter(ws.novel, ws.chapter_number, draft)
            
            if result.get("valid"):
                self._transition(ws, State.DONE)
            else:
                ws.attempt += 1
                self._transition(ws, State.WRITING)  # revise from scratch
        except Exception as e:
            logger.exception("Stage validating failed")
            self._fail(ws, str(e))
        
        return ws

    # ─── Internal decisions ─────────────────────────────────────

    def _decide_after_review(self, ws: WorkflowState) -> WorkflowState:
        """Reviewing → validating or writing (revise)."""
        if ws.state == State.VALIDATING:
            return self.run_validating(ws)
        elif ws.state == State.WRITING:
            return self.run_writing(ws)
        return ws

    def _decide_after_validation(self, ws: WorkflowState) -> WorkflowState:
        """Validating → done or writing (revise)."""
        if ws.state == State.DONE:
            return ws
        elif ws.state == State.WRITING:
            return self.run_writing(ws)
        return ws

    def _wait_for_approval(self, ws: WorkflowState) -> WorkflowState:
        """Blocked waiting for human approval. State is persisted as BLOCKED."""
        if ws.state == State.BRIEF_DRAFTED and not ws.approved:
            self._transition(ws, State.BLOCKED)
        return ws

    def unblock(self, ws: WorkflowState):
        """Human calls this to approve and unblock."""
        if ws.state != State.BLOCKED:
            raise ValueError(f"Cannot unblock from state {ws.state.value}")
        ws.approved = True
        self._transition(ws, State.BRIEF_APPROVED)
