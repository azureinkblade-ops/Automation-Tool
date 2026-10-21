# Chapter Workflow API — semantic routes (no arbitrary state setting)

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Feature flag (mirrors ENABLE_AGENT_POSTS pattern)
def chapter_workflow_enabled() -> bool:
    return str(os.environ.get("ENABLE_CHAPTER_WORKFLOW", "0")).strip().lower() not in {"", "0", "false", "no", "off"}


class ChapterWorkflowAPI:
    """Semantic API for chapter workflows.
    
    Routes:
      POST /api/chapter-workflow/start    — create new workflow, run context_loaded
      POST /api/chapter-workflow/advance  — run current stage
      POST /api/chapter-workflow/approve  — approve brief and unblock
      GET  /api/chapter-workflow/status   — get current state
      GET  /api/chapter-workflow/list     — list active workflows
      
    NOT exposed:
      - set_state (never allow arbitrary state jumps)
      - retry (handled internally by revision loops)
      - delete (workflows are permanent audit records)
    """
    
    def __init__(
        self,
        controller,  # ChapterWorkflowController
        output_root: Path,
    ):
        self.controller = controller
        self.output_root = output_root

    def start(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workflow and run the first stage."""
        abbr = str(body.get("abbr") or "").strip().upper()
        chapter = body.get("chapter_number")
        
        if not abbr:
            return {"error": "abbr is required"}, 400
        
        if chapter is None:
            return {"error": "chapter_number is required"}, 400
        
        try:
            chapter = int(chapter)
        except (ValueError, TypeError):
            return {"error": "chapter_number must be an integer"}, 400
        
        # Check for existing active workflow for this chapter
        existing = self.controller.store.load(f"{abbr}-{chapter}")
        if existing and existing.state.value not in ("done", "failed"):
            return {
                "workflow_id": existing.workflow_id,
                "state": existing.state.value,
                "message": "Workflow already exists",
            }, 200
        
        ws = self.controller.create(abbr, chapter)
        self.controller.run_context_loaded(ws)
        
        return {
            "workflow_id": ws.workflow_id,
            "state": ws.state.value,
            "chapter_number": ws.chapter_number,
        }, 201

    def advance(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run the current stage."""
        workflow_id = str(body.get("workflow_id") or "").strip()
        if not workflow_id:
            return {"error": "workflow_id is required"}, 400
        
        ws = self.controller.store.load(workflow_id)
        if not ws:
            return {"error": f"Workflow {workflow_id} not found"}, 404
        
        if ws.state.value in ("done", "failed"):
            return {
                "workflow_id": ws.workflow_id,
                "state": ws.state.value,
                "message": "Workflow is complete or failed",
            }, 200
        
        if ws.state.value == "blocked":
            return {
                "workflow_id": ws.workflow_id,
                "state": ws.state.value,
                "message": "Workflow is blocked waiting for approval. Use /api/chapter-workflow/approve",
            }, 200
        
        self.controller.run_stage(ws)
        
        return {
            "workflow_id": ws.workflow_id,
            "state": ws.state.value,
            "previous_state": ws.previous_state.value if ws.previous_state else None,
            "attempt": ws.attempt,
        }, 200

    def approve(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Approve the brief and unblock the workflow."""
        workflow_id = str(body.get("workflow_id") or "").strip()
        if not workflow_id:
            return {"error": "workflow_id is required"}, 400
        
        ws = self.controller.store.load(workflow_id)
        if not ws:
            return {"error": f"Workflow {workflow_id} not found"}, 404
        
        if ws.state.value != "blocked":
            return {
                "workflow_id": ws.workflow_id,
                "state": ws.state.value,
                "error": "Workflow is not blocked. Only blocked workflows can be approved.",
            }, 400
        
        self.controller.unblock(ws)
        
        return {
            "workflow_id": ws.workflow_id,
            "state": ws.state.value,
            "message": "Workflow approved and unblocked",
        }, 200

    def status(self, workflow_id: str) -> Dict[str, Any]:
        """Get current workflow state."""
        ws = self.controller.store.load(workflow_id)
        if not ws:
            return {"error": f"Workflow {workflow_id} not found"}, 404
        
        return {
            "workflow_id": ws.workflow_id,
            "novel": ws.novel,
            "chapter_number": ws.chapter_number,
            "state": ws.state.value,
            "previous_state": ws.previous_state.value if ws.previous_state else None,
            "attempt": ws.attempt,
            "artifacts": ws.artifacts,
            "approval_required": ws.approval_required,
            "approved": ws.approved,
            "last_error": ws.last_error,
            "created_at": ws.created_at,
            "updated_at": ws.updated_at,
        }, 200

    def list_active(self) -> Dict[str, Any]:
        """List all active (non-terminal) workflows."""
        workflows = self.controller.store.list_active()
        return {
            "workflows": [
                {
                    "workflow_id": ws.workflow_id,
                    "novel": ws.novel,
                    "chapter_number": ws.chapter_number,
                    "state": ws.state.value,
                    "updated_at": ws.updated_at,
                }
                for ws in workflows
            ],
            "count": len(workflows),
        }, 200
