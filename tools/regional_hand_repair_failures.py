"""EA-4D.4F Regional Hand Repair failure ownership matrix.

This module documents the explicit ownership of every failure category.
Typed errors are evidence categories; this matrix assigns organizational ownership.

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md (section 11)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from tools.regional_hand_repair import (
    RepairFindingsError,
    RepairRegionError,
    RepairIdentityError,
    RepairEligibilityError,
    RepairAssetError,
    RepairGpuAuthorityAbsent,
    RepairDuplicateSubmission,
    RepairImmutabilityViolation,
    RepairSoulbladeViolation,
    RepairCandidateContentError,
    RegionalHandRepairError,
)
from tools.regional_hand_repair_workflow import WorkflowValidationError
from tools.regional_hand_repair_evidence import (
    DuplicateRequestError,
    InvalidStateTransitionError,
    RecordNotFoundError,
    EvidenceStoreError,
)
from tools.regional_hand_repair_adapter import (
    EndpointNotAllowedError,
    WorkflowNotAllowedError,
    TransportNotConfiguredError,
    AdapterError,
)
from tools.regional_hand_repair_submission import (
    SubmissionError,
    WorkflowRejectedError,
    TransportUnavailableError,
    UncertainSubmissionError,
    DuplicateSubmissionError,
)


# ---------------------------------------------------------------------------
# Failure ownership record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureOwnership:
    """Ownership record for a single failure category."""
    category: str
    detecting_component: str
    owning_component: str
    retry_eligible: bool
    cleanup_required: bool
    externally_visible: str


# ---------------------------------------------------------------------------
# Failure ownership matrix
# ---------------------------------------------------------------------------

FAILURE_MATRIX: Dict[str, FailureOwnership] = {
    # Request validation
    "malformed_pilot_request": FailureOwnership(
        category="malformed_pilot_request",
        detecting_component="pilot composition root",
        owning_component="pilot composition root",
        retry_eligible=True,
        cleanup_required=False,
        externally_visible="validation error",
    ),
    "invalid_canonical_input": FailureOwnership(
        category="invalid_canonical_input",
        detecting_component="pilot composition root",
        owning_component="pilot composition root",
        retry_eligible=True,
        cleanup_required=False,
        externally_visible="validation error",
    ),
    # Governance
    "governance_acceptance_missing": FailureOwnership(
        category="governance_acceptance_missing",
        detecting_component="authorization issuance",
        owning_component="governance/authorization owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="acceptance lineage",
    ),
    "authorization_denied": FailureOwnership(
        category="authorization_denied",
        detecting_component="authorization engine",
        owning_component="authorization owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="terminal decision",
    ),
    "claim_invalid": FailureOwnership(
        category="claim_invalid",
        detecting_component="authority store",
        owning_component="authorization owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="claim record",
    ),
    # Routing
    "no_eligible_worker": FailureOwnership(
        category="no_eligible_worker",
        detecting_component="worker router",
        owning_component="registry/routing owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="route error",
    ),
    "worker_version_mismatch": FailureOwnership(
        category="worker_version_mismatch",
        detecting_component="launch admission",
        owning_component="registry/routing owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="mismatch evidence",
    ),
    "runtime_binding_mismatch": FailureOwnership(
        category="runtime_binding_mismatch",
        detecting_component="launch admission",
        owning_component="runtime-binding owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="binding error",
    ),
    # Material validation
    "source_mask_model_template_hash_mismatch": FailureOwnership(
        category="source_mask_model_template_hash_mismatch",
        detecting_component="pilot worker preflight",
        owning_component="workload material owner",
        retry_eligible=True,
        cleanup_required=False,
        externally_visible="expected/actual hashes",
    ),
    "workflow_template_mismatch": FailureOwnership(
        category="workflow_template_mismatch",
        detecting_component="workflow validator",
        owning_component="workflow manifest owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="template hash mismatch",
    ),
    "node_allowlist_violation": FailureOwnership(
        category="node_allowlist_violation",
        detecting_component="workflow validator",
        owning_component="workflow manifest owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="prohibited node",
    ),
    "model_mismatch": FailureOwnership(
        category="model_mismatch",
        detecting_component="pilot worker preflight",
        owning_component="workload material owner",
        retry_eligible=True,
        cleanup_required=False,
        externally_visible="expected/actual model",
    ),
    # GPU
    "gpu_authority_absent": FailureOwnership(
        category="gpu_authority_absent",
        detecting_component="pilot root/worker",
        owning_component="GPU authority owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="refusal record",
    ),
    # Runtime
    "comfyui_unreachable": FailureOwnership(
        category="comfyui_unreachable",
        detecting_component="runtime adapter",
        owning_component="runtime operations owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="normalized adapter error",
    ),
    "submit_response_lost": FailureOwnership(
        category="submit_response_lost",
        detecting_component="coordinator",
        owning_component="runtime adapter owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="canonical key lookup",
    ),
    "runtime_unknown": FailureOwnership(
        category="runtime_unknown",
        detecting_component="coordinator",
        owning_component="runtime adapter owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="uncertain submission",
    ),
    "runtime_failed": FailureOwnership(
        category="runtime_failed",
        detecting_component="coordinator",
        owning_component="runtime adapter owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="runtime failure",
    ),
    # Output validation
    "output_missing": FailureOwnership(
        category="output_missing",
        detecting_component="workload verifier",
        owning_component="regional hand-repair owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="missing output",
    ),
    "provenance_invalid": FailureOwnership(
        category="provenance_invalid",
        detecting_component="workload verifier",
        owning_component="regional hand-repair owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="invalid provenance",
    ),
    "immutability_violation": FailureOwnership(
        category="immutability_violation",
        detecting_component="immutability verifier",
        owning_component="regional hand-repair owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="changed pixel evidence",
    ),
    "soulblade_violation": FailureOwnership(
        category="soulblade_violation",
        detecting_component="protected-object verifier",
        owning_component="regional hand-repair owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="changed pixel evidence",
    ),
    "classifier_fail": FailureOwnership(
        category="classifier_fail",
        detecting_component="visual classifier",
        owning_component="content-quality owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="FAIL disposition",
    ),
    # Persistence
    "result_persistence_failure": FailureOwnership(
        category="result_persistence_failure",
        detecting_component="pilot root",
        owning_component="pilot root/storage owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="launch/runtime/result lineage",
    ),
    # Post-launch
    "post_launch_projection_failure": FailureOwnership(
        category="post_launch_projection_failure",
        detecting_component="existing orchestrator",
        owning_component="state projector owner",
        retry_eligible=False,
        cleanup_required=False,
        externally_visible="projection error",
    ),
    # Cleanup
    "cleanup_failure": FailureOwnership(
        category="cleanup_failure",
        detecting_component="pilot root",
        owning_component="runtime operations owner",
        retry_eligible=True,
        cleanup_required=False,
        externally_visible="cleanup response",
    ),
}


# ---------------------------------------------------------------------------
# Error-to-ownership mapping
# ---------------------------------------------------------------------------

ERROR_TO_OWNERSHIP: Dict[type, str] = {
    # Request validation
    RepairFindingsError: "invalid_canonical_input",
    RepairRegionError: "invalid_canonical_input",
    RepairIdentityError: "invalid_canonical_input",
    RepairEligibilityError: "invalid_canonical_input",
    RepairAssetError: "invalid_canonical_input",
    # GPU
    RepairGpuAuthorityAbsent: "gpu_authority_absent",
    # Duplicate
    RepairDuplicateSubmission: "submit_response_lost",
    DuplicateRequestError: "submit_response_lost",
    DuplicateSubmissionError: "submit_response_lost",
    # Immutability
    RepairImmutabilityViolation: "immutability_violation",
    RepairSoulbladeViolation: "soulblade_violation",
    RepairCandidateContentError: "classifier_fail",
    # Workflow
    WorkflowValidationError: "workflow_template_mismatch",
    WorkflowNotAllowedError: "workflow_template_mismatch",
    WorkflowRejectedError: "workflow_template_mismatch",
    # Adapter
    EndpointNotAllowedError: "comfyui_unreachable",
    TransportNotConfiguredError: "comfyui_unreachable",
    TransportUnavailableError: "comfyui_unreachable",
    # Submission
    SubmissionError: "submit_response_lost",
    UncertainSubmissionError: "runtime_unknown",
    # Evidence
    InvalidStateTransitionError: "result_persistence_failure",
    RecordNotFoundError: "result_persistence_failure",
    EvidenceStoreError: "result_persistence_failure",
}


def get_ownership(error: Exception) -> Optional[FailureOwnership]:
    """Get the failure ownership for a given error."""
    for error_type, category in ERROR_TO_OWNERSHIP.items():
        if isinstance(error, error_type):
            return FAILURE_MATRIX.get(category)
    return None


def get_all_ownerships() -> Dict[str, FailureOwnership]:
    """Return the complete failure ownership matrix."""
    return dict(FAILURE_MATRIX)
