"""Tests for EA-4D.4F Regional Hand Repair failure ownership matrix."""

import pytest

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
)
from tools.regional_hand_repair_submission import (
    SubmissionError,
    WorkflowRejectedError,
    TransportUnavailableError,
    UncertainSubmissionError,
    DuplicateSubmissionError,
)
from tools.regional_hand_repair_failures import (
    FailureOwnership,
    FAILURE_MATRIX,
    ERROR_TO_OWNERSHIP,
    get_ownership,
    get_all_ownerships,
)


class TestFailureMatrix:
    def test_all_matrix_entries_are_failure_ownership(self):
        for key, value in FAILURE_MATRIX.items():
            assert isinstance(value, FailureOwnership)

    def test_all_matrix_keys_match_category(self):
        for key, value in FAILURE_MATRIX.items():
            assert key == value.category

    def test_all_error_types_mapped(self):
        for error_type, category in ERROR_TO_OWNERSHIP.items():
            assert category in FAILURE_MATRIX


class TestGetOwnership:
    def test_findings_error_maps(self):
        error = RepairFindingsError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "invalid_canonical_input"

    def test_region_error_maps(self):
        error = RepairRegionError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "invalid_canonical_input"

    def test_identity_error_maps(self):
        error = RepairIdentityError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "invalid_canonical_input"

    def test_eligibility_error_maps(self):
        error = RepairEligibilityError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "invalid_canonical_input"

    def test_asset_error_maps(self):
        error = RepairAssetError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "invalid_canonical_input"

    def test_gpu_authority_absent_maps(self):
        error = RepairGpuAuthorityAbsent("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "gpu_authority_absent"

    def test_duplicate_submission_maps(self):
        error = RepairDuplicateSubmission("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "submit_response_lost"

    def test_immutability_violation_maps(self):
        error = RepairImmutabilityViolation("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "immutability_violation"

    def test_soulblade_violation_maps(self):
        error = RepairSoulbladeViolation("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "soulblade_violation"

    def test_candidate_content_error_maps(self):
        error = RepairCandidateContentError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "classifier_fail"

    def test_workflow_validation_error_maps(self):
        error = WorkflowValidationError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "workflow_template_mismatch"

    def test_duplicate_request_error_maps(self):
        error = DuplicateRequestError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "submit_response_lost"

    def test_endpoint_not_allowed_maps(self):
        error = EndpointNotAllowedError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "comfyui_unreachable"

    def test_transport_not_configured_maps(self):
        error = TransportNotConfiguredError("test")
        ownership = get_ownership(error)
        assert ownership is not None
        assert ownership.category == "comfyui_unreachable"

    def test_unknown_error_returns_none(self):
        class UnknownError(Exception):
            pass
        error = UnknownError("test")
        ownership = get_ownership(error)
        assert ownership is None


class TestGetAllOwnerships:
    def test_returns_dict(self):
        result = get_all_ownerships()
        assert isinstance(result, dict)

    def test_contains_expected_categories(self):
        result = get_all_ownerships()
        expected = [
            "malformed_pilot_request",
            "invalid_canonical_input",
            "governance_acceptance_missing",
            "authorization_denied",
            "gpu_authority_absent",
            "comfyui_unreachable",
            "submit_response_lost",
            "runtime_unknown",
            "runtime_failed",
            "immutability_violation",
            "soulblade_violation",
            "classifier_fail",
            "result_persistence_failure",
            "cleanup_failure",
        ]
        for category in expected:
            assert category in result, f"missing category: {category}"


class TestOwnershipProperties:
    def test_non_retryable_categories(self):
        non_retryable = [
            "governance_acceptance_missing",
            "authorization_denied",
            "no_eligible_worker",
            "worker_version_mismatch",
            "runtime_binding_mismatch",
            "gpu_authority_absent",
            "comfyui_unreachable",
            "submit_response_lost",
            "runtime_unknown",
            "runtime_failed",
            "immutability_violation",
            "soulblade_violation",
            "classifier_fail",
            "result_persistence_failure",
            "post_launch_projection_failure",
        ]
        for category in non_retryable:
            ownership = FAILURE_MATRIX[category]
            assert not ownership.retry_eligible, f"{category} should not be retryable"

    def test_retryable_categories(self):
        retryable = [
            "malformed_pilot_request",
            "invalid_canonical_input",
            "source_mask_model_template_hash_mismatch",
            "model_mismatch",
            "cleanup_failure",
        ]
        for category in retryable:
            ownership = FAILURE_MATRIX[category]
            assert ownership.retry_eligible, f"{category} should be retryable"
