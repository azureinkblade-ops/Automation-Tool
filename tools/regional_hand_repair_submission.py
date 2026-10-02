"""EA-4D.4F crash-safe Regional Hand Repair submission orchestrator.

This module implements crash-safe submission handling:
- Before submit: persist durable intent
- Submit: exactly one constrained workflow request
- Response received: persist runtime identity/evidence
- Response uncertain/lost: DO NOT resubmit blindly, use lookup-only reconciliation

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    .hermes/handoffs/ea4d4f/step-2-evidence-store.md

Authority limits:
    CPU-only. No GPU, no ComfyUI client, no submission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from tools.regional_hand_repair_evidence import (
    RegionalHandRepairEvidenceStore,
    DuplicateRequestError,
)
from tools.regional_hand_repair_adapter import (
    RegionalHandRepairComfyUIAdapter,
    WorkflowNotAllowedError,
    TransportNotConfiguredError,
)
from tools.regional_hand_repair_workflow import (
    build_frozen_template,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SubmissionError(Exception):
    """Base class for submission errors."""


class WorkflowRejectedError(SubmissionError):
    """The workflow was rejected by validation."""


class TransportUnavailableError(SubmissionError):
    """The transport is not available."""


class UncertainSubmissionError(SubmissionError):
    """The submission outcome is uncertain."""


class DuplicateSubmissionError(SubmissionError):
    """This repair has already been submitted."""


# ---------------------------------------------------------------------------
# Submission orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmissionResult:
    """Result of a submission attempt."""
    prompt_id: str
    filename: str
    subfolder: str
    type: str


class RegionalHandRepairSubmissionOrchestrator:
    """Crash-safe submission orchestrator for Regional Hand Repair.

    Ensures exactly-one submission semantics:
    - Before submit: persist durable intent (RECORDED -> SUBMITTING)
    - Submit: exactly one constrained workflow request
    - Response received: persist runtime identity (SUBMITTING -> STARTED)
    - Response uncertain: mark SUBMISSION_UNKNOWN, use lookup-only reconciliation
    """

    def __init__(
        self,
        evidence_store: RegionalHandRepairEvidenceStore,
        adapter: RegionalHandRepairComfyUIAdapter,
    ) -> None:
        self._evidence = evidence_store
        self._adapter = adapter

    def submit(
        self,
        *,
        launch_attempt_id: str,
        idempotency_key: str,
        repair_execution_id: str,
        task_input_sha256: str,
        worker_id: str,
        worker_version: str,
        runtime_binding_id: str,
        workflow: Dict[str, Any],
    ) -> SubmissionResult:
        """Submit a repair workflow with crash-safe semantics.

        If a record with the same idempotency key already exists:
        - If it has a definitive STARTED result, return that result without resubmission
        - If it has a definitive FAILED result, raise DuplicateSubmissionError
        - If the outcome is uncertain, perform lookup/reconciliation only

        Args:
            launch_attempt_id: The canonical launch attempt ID
            idempotency_key: The deterministic idempotency key
            repair_execution_id: The repair execution ID
            task_input_sha256: The task input hash
            worker_id: The worker ID
            worker_version: The worker version
            runtime_binding_id: The runtime binding ID
            workflow: The workflow dict to submit

        Returns:
            SubmissionResult with prompt_id and output locator

        Raises:
            DuplicateSubmissionError: if the repair has already been submitted
            WorkflowRejectedError: if the workflow fails validation
            TransportUnavailableError: if the transport is not available
        """
        # Check for existing record
        existing = self._evidence.get_repair_run_by_idempotency(idempotency_key)
        if existing is not None:
            return self._replay_existing(existing)

        # Validate workflow before persisting intent
        try:
            self._adapter.validate_workflow_envelope(workflow)
        except WorkflowNotAllowedError as exc:
            raise WorkflowRejectedError(str(exc)) from exc

        # Persist durable intent (RECORDED)
        self._evidence.create_repair_run(
            launch_attempt_id=launch_attempt_id,
            idempotency_key=idempotency_key,
            repair_execution_id=repair_execution_id,
            task_input_sha256=task_input_sha256,
            worker_id=worker_id,
            worker_version=worker_version,
            runtime_binding_id=runtime_binding_id,
        )

        # Transition to SUBMITTING
        self._evidence.transition_state(launch_attempt_id, "SUBMITTING")

        # Submit exactly one constrained workflow request
        try:
            response = self._adapter.submit_workflow(workflow)
        except TransportNotConfiguredError as exc:
            self._evidence.transition_state(launch_attempt_id, "SUBMISSION_UNKNOWN")
            raise TransportUnavailableError(str(exc)) from exc

        # Response received: persist runtime identity
        prompt_id = response["prompt_id"]
        self._evidence.transition_state(
            launch_attempt_id, "STARTED", runtime_run_id=prompt_id
        )

        # Get history to find output filename
        history = self._adapter.get_history(prompt_id)
        output_locator = self._extract_output_locator(history)

        return SubmissionResult(
            prompt_id=prompt_id,
            filename=output_locator["filename"],
            subfolder=output_locator.get("subfolder", ""),
            type=output_locator.get("type", "output"),
        )

    def _replay_existing(self, existing: Any) -> SubmissionResult:
        """Replay an existing record without resubmission."""
        if existing.state == "STARTED" or existing.state == "OUTPUT_CAPTURED" or existing.state == "VERIFIED":
            # Definitive success: return existing result
            result_json = existing.result_json
            if result_json:
                result = json.loads(result_json)
                return SubmissionResult(
                    prompt_id=result["prompt_id"],
                    filename=result["filename"],
                    subfolder=result.get("subfolder", ""),
                    type=result.get("type", "output"),
                )
            # STARTED may not have result_json yet (only runtime_run_id)
            if existing.state == "STARTED" and existing.runtime_run_id:
                return SubmissionResult(
                    prompt_id=existing.runtime_run_id,
                    filename="",
                    subfolder="",
                    type="output",
                )
            # Should not happen: terminal state without result
            raise UncertainSubmissionError(
                f"existing record {existing.launch_attempt_id!r} has state {existing.state!r} "
                f"but no result"
            )
        elif existing.state == "FAILED":
            raise DuplicateSubmissionError(
                f"repair {existing.launch_attempt_id!r} has already failed"
            )
        elif existing.state == "SUBMISSION_UNKNOWN":
            # Uncertain: perform lookup/reconciliation only
            raise UncertainSubmissionError(
                f"repair {existing.launch_attempt_id!r} has uncertain submission state"
            )
        else:
            # RECORDED, SUBMITTING: in-progress
            raise DuplicateSubmissionError(
                f"repair {existing.launch_attempt_id!r} is already in progress (state: {existing.state!r})"
            )

    def _extract_output_locator(self, history: Dict[str, Any]) -> Dict[str, str]:
        """Extract the output locator from a history response."""
        outputs = history.get("outputs", {})
        # Look for the SaveImage node output
        for node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            if images:
                image = images[0]
                return {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                }
        raise SubmissionError("no output image found in history")


def create_submission_orchestrator(
    evidence_db_path: str,
    transport: Any = None,
) -> RegionalHandRepairSubmissionOrchestrator:
    """Factory function to create a submission orchestrator."""
    evidence_store = RegionalHandRepairEvidenceStore(evidence_db_path)
    adapter = RegionalHandRepairComfyUIAdapter(transport=transport)
    return RegionalHandRepairSubmissionOrchestrator(evidence_store, adapter)
