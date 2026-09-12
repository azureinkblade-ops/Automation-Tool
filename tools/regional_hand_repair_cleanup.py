"""EA-4D.4F Regional Hand Repair cleanup ownership.

This module implements the cleanup coordination logic.
The pilot composition root owns batch cleanup coordination.
The worker may report resource state but may not decide that the enclosing batch is complete.

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md (section 10)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tools.regional_hand_repair_evidence import RegionalHandRepairEvidenceStore


# ---------------------------------------------------------------------------
# Cleanup errors
# ---------------------------------------------------------------------------


class CleanupError(Exception):
    """Base class for cleanup errors."""


class CleanupPreconditionsNotMetError(CleanupError):
    """Cleanup preconditions are not met."""


class CleanupRecordError(CleanupError):
    """Failed to record cleanup state."""


# ---------------------------------------------------------------------------
# Cleanup ownership
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanupResult:
    """Result of a cleanup operation."""
    success: bool
    models_unloaded: bool
    memory_freed: bool
    comfyui_reachable: bool
    error: Optional[str] = None


class RegionalHandRepairCleanupOrchestrator:
    """Orchestrates cleanup for Regional Hand Repair pilot.

    Cleanup preconditions (ALL must be met):
    - Every authorized operation in the batch has a terminal workload result
    - Required result and provenance evidence is durable
    - No runtime reconciliation remains pending
    - No later authorized GPU operation exists in the batch

    Frozen future runtime action:
    - POST /free with {"unload_models": true, "free_memory": true}
    - Verify ComfyUI remains reachable
    - Record: models unloaded, VRAM release requested
    """

    def __init__(self, evidence_store: RegionalHandRepairEvidenceStore) -> None:
        self._evidence = evidence_store

    def check_preconditions(self, launch_attempt_id: str) -> tuple[bool, list[str]]:
        """Check if cleanup preconditions are met.

        Returns:
            (met, list of unmet conditions)
        """
        unmet: list[str] = []

        run = self._evidence.get_repair_run(launch_attempt_id)
        if run is None:
            unmet.append(f"repair run {launch_attempt_id!r} not found")
            return False, unmet

        # Check terminal state
        if run.state not in ("VERIFIED", "FAILED"):
            unmet.append(f"repair run {launch_attempt_id!r} is not in terminal state (current: {run.state!r})")

        # Check result durability
        if run.state == "VERIFIED":
            if not run.result_json:
                unmet.append(f"repair run {launch_attempt_id!r} is VERIFIED but has no result_json")
            if not run.result_sha256:
                unmet.append(f"repair run {launch_attempt_id!r} is VERIFIED but has no result_sha256")

        # Check no pending reconciliation
        if run.state == "SUBMISSION_UNKNOWN":
            unmet.append(f"repair run {launch_attempt_id!r} has uncertain submission state")

        return len(unmet) == 0, unmet

    def record_cleanup_eligible(self, launch_attempt_id: str) -> None:
        """Record that cleanup is eligible for this repair run."""
        if self.is_cleanup_eligible(launch_attempt_id):
            return
        self._evidence.append_event(
            launch_attempt_id,
            "CLEANUP_ELIGIBLE",
            "{}",
        )

    def record_cleanup_complete(
        self,
        launch_attempt_id: str,
        *,
        models_unloaded: bool,
        memory_freed: bool,
        comfyui_reachable: bool,
    ) -> None:
        """Record that cleanup is complete."""
        if self.is_cleanup_complete(launch_attempt_id):
            return
        event_json = json.dumps({
            "models_unloaded": models_unloaded,
            "memory_freed": memory_freed,
            "comfyui_reachable": comfyui_reachable,
        })
        self._evidence.append_event(
            launch_attempt_id,
            "CLEANUP_COMPLETE",
            event_json,
        )

    def record_cleanup_failure(self, launch_attempt_id: str, error: str) -> None:
        """Record a cleanup failure."""
        event_json = json.dumps({"error": error})
        self._evidence.append_event(
            launch_attempt_id,
            "CLEANUP_FAILURE",
            event_json,
        )

    def is_cleanup_eligible(self, launch_attempt_id: str) -> bool:
        """Check if cleanup has been marked eligible."""
        events = self._evidence.get_events(launch_attempt_id)
        return any(e.event_type == "CLEANUP_ELIGIBLE" for e in events)

    def is_cleanup_complete(self, launch_attempt_id: str) -> bool:
        """Check if cleanup has been marked complete."""
        events = self._evidence.get_events(launch_attempt_id)
        return any(e.event_type == "CLEANUP_COMPLETE" for e in events)
