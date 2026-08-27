"""Tests for EA-4D.4F frozen Regional Hand Repair workflow manifest and validator."""

import pytest

from tools.regional_hand_repair_workflow import (
    ALLOWED_NODE_CLASSES,
    REQUIRED_NODE_CLASSES,
    CANONICAL_REPAIR_TEMPLATE,
    FROZEN_TEMPLATE_HASH,
    WorkflowValidationError,
    UnknownNodeClassError,
    MissingRequiredNodeError,
    ExceededNodeCountError,
    TemplateHashMismatchError,
    ProhibitedNodeError,
    ValidationResult,
    validate_workflow,
    validate_workflow_strict,
    build_frozen_template,
    get_frozen_template_hash,
    get_allowed_node_classes,
    get_required_node_classes,
)


class TestFrozenTemplate:
    def test_frozen_template_is_valid(self):
        """The canonical template must pass its own validation."""
        result = validate_workflow(CANONICAL_REPAIR_TEMPLATE)
        assert result.valid, f"errors: {result.errors}"

    def test_frozen_template_hash_is_deterministic(self):
        """Template hash must be deterministic."""
        hash1 = get_frozen_template_hash()
        hash2 = get_frozen_template_hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_frozen_template_strict_valid(self):
        """Strict validation must pass for the canonical template."""
        result = validate_workflow_strict(CANONICAL_REPAIR_TEMPLATE)
        assert result.valid, f"errors: {result.errors}"


class TestAllowedNodes:
    def test_checkpoint_is_allowed(self):
        assert "CheckpointLoaderSimple" in ALLOWED_NODE_CLASSES

    def test_lora_is_allowed(self):
        assert "LoraLoader" in ALLOWED_NODE_CLASSES

    def test_ksampler_is_allowed(self):
        assert "KSampler" in ALLOWED_NODE_CLASSES

    def test_custom_node_is_not_allowed(self):
        assert "CustomNode" not in ALLOWED_NODE_CLASSES

    def test_shell_node_is_not_allowed(self):
        assert "ShellExecute" not in ALLOWED_NODE_CLASSES


class TestRequiredNodes:
    def test_checkpoint_is_required(self):
        assert "CheckpointLoaderSimple" in REQUIRED_NODE_CLASSES

    def test_ksampler_is_required(self):
        assert "KSampler" in REQUIRED_NODE_CLASSES

    def test_custom_node_is_not_required(self):
        assert "CustomNode" not in REQUIRED_NODE_CLASSES


class TestValidation:
    def test_valid_workflow_passes(self):
        workflow = build_frozen_template()
        result = validate_workflow(workflow)
        assert result.valid

    def test_empty_workflow_fails(self):
        result = validate_workflow({})
        assert not result.valid

    def test_prohibited_node_fails(self):
        workflow = build_frozen_template()
        workflow["nodes"]["X1"] = {"class_type": "CustomNode", "inputs": {}}
        result = validate_workflow(workflow)
        assert not result.valid
        assert any("prohibited" in e.lower() or "CustomNode" in e for e in result.errors)

    def test_missing_required_node_fails(self):
        workflow = build_frozen_template()
        del workflow["nodes"]["R0"]  # Remove checkpoint
        result = validate_workflow(workflow)
        assert not result.valid
        assert any("missing required" in e.lower() for e in result.errors)

    def test_too_many_ksamplers_fails(self):
        workflow = build_frozen_template()
        workflow["nodes"]["R7B"] = {
            "class_type": "KSampler",
            "inputs": {"seed": 0, "steps": 20, "cfg": 4.5},
        }
        result = validate_workflow(workflow)
        assert not result.valid
        assert any("too many KSampler" in e for e in result.errors)

    def test_too_many_saveimages_fails(self):
        workflow = build_frozen_template()
        workflow["nodes"]["R9B"] = {
            "class_type": "SaveImage",
            "inputs": {"images": ["R8", 0], "filename_prefix": "extra"},
        }
        result = validate_workflow(workflow)
        assert not result.valid
        assert any("too many SaveImage" in e for e in result.errors)

    def test_too_many_loadmasks_fails(self):
        workflow = build_frozen_template()
        workflow["nodes"]["R5B"] = {
            "class_type": "LoadImageMask",
            "inputs": {"image": "extra_mask.png", "channel": "red"},
        }
        result = validate_workflow(workflow)
        assert not result.valid
        assert any("too many LoadImageMask" in e for e in result.errors)

    def test_strict_validation_rejects_modified_structure(self):
        """Changing a node's connections should fail strict validation."""
        workflow = build_frozen_template()
        workflow["nodes"]["R7"]["inputs"]["latent_image"] = ["R6T", 0]  # Modified
        result = validate_workflow_strict(workflow)
        assert not result.valid
        assert any("hash mismatch" in e.lower() for e in result.errors)


class TestBuilder:
    def test_build_frozen_template_returns_copy(self):
        t1 = build_frozen_template()
        t2 = build_frozen_template()
        assert t1 is not t2
        assert t1 == t2

    def test_frozen_template_has_correct_meta(self):
        template = build_frozen_template()
        assert template["v2_meta"]["id"] == "regional_hand_repair_inpaint"
        assert template["v2_meta"]["version"] == "1.0"


class TestHashPreimage:
    def test_frozen_template_hash_matches(self):
        """The frozen hash must match the computed hash of the template."""
        template = build_frozen_template()
        result = validate_workflow(template)
        assert result.valid
        assert result.template_hash == FROZEN_TEMPLATE_HASH
