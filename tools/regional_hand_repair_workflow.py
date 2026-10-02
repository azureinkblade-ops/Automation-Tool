"""EA-4D.4F frozen Regional Hand Repair workflow manifest and validator.

This module freezes the canonical Regional Hand Repair workflow template,
node allowlist, and validation contract. It is the source of truth for
what constitutes an authorized repair workflow.

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    EA-4D.4F-R6-DESIGN_HANDOFF.md

Authority limits:
    CPU-only. No GPU, no ComfyUI client, no submission.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Tuple

from tools.regional_hand_repair import (
    REPAIR_WORKFLOW_TEMPLATE_ID,
    REPAIR_WORKFLOW_VERSION,
    REPAIR_NODE_CLASS_CHECKPOINT,
    REPAIR_NODE_CLASS_LORA,
    REPAIR_NODE_CLASS_CLIPENC,
    REPAIR_NODE_CLASS_LOADIMAGE,
    REPAIR_NODE_CLASS_LOADMASK,
    REPAIR_NODE_CLASS_VAEENCODEINPAINT,
    REPAIR_NODE_CLASS_KSAMPLER,
    REPAIR_NODE_CLASS_VAEDECODE,
    REPAIR_NODE_CLASS_SAVEIMAGE,
    REPAIR_NODE_CLASS_VAEENCODE,
    REPAIR_NODE_CLASS_SETLATENTNOISEMASK,
    REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT,
    REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK,
)


# ---------------------------------------------------------------------------
# Frozen node allowlist
# ---------------------------------------------------------------------------

# Node classes permitted in an authorized repair workflow.
ALLOWED_NODE_CLASSES: FrozenSet[str] = frozenset({
    REPAIR_NODE_CLASS_CHECKPOINT,
    REPAIR_NODE_CLASS_LORA,
    REPAIR_NODE_CLASS_CLIPENC,
    REPAIR_NODE_CLASS_LOADIMAGE,
    REPAIR_NODE_CLASS_LOADMASK,
    REPAIR_NODE_CLASS_VAEENCODEINPAINT,
    REPAIR_NODE_CLASS_KSAMPLER,
    REPAIR_NODE_CLASS_VAEDECODE,
    REPAIR_NODE_CLASS_SAVEIMAGE,
    REPAIR_NODE_CLASS_VAEENCODE,
    REPAIR_NODE_CLASS_SETLATENTNOISEMASK,
})

# Required node classes (must be present in every authorized workflow).
REQUIRED_NODE_CLASSES: FrozenSet[str] = frozenset({
    REPAIR_NODE_CLASS_CHECKPOINT,
    REPAIR_NODE_CLASS_LORA,
    REPAIR_NODE_CLASS_CLIPENC,
    REPAIR_NODE_CLASS_LOADIMAGE,
    REPAIR_NODE_CLASS_LOADMASK,
    REPAIR_NODE_CLASS_KSAMPLER,
    REPAIR_NODE_CLASS_VAEDECODE,
    REPAIR_NODE_CLASS_SAVEIMAGE,
})

# Exactly one KSampler is permitted.
MAX_KSAMPLER_COUNT = 1

# Exactly one SaveImage is permitted.
MAX_SAVEIMAGE_COUNT = 1

# Exactly one LoadImageMask is permitted.
MAX_LOADMASK_COUNT = 1


# ---------------------------------------------------------------------------
# Frozen template
# ---------------------------------------------------------------------------

# The canonical repair workflow template (CONTROL architecture).
# This is the frozen graph that all authorized repair workflows must match
# (modulo the encode-architecture branch and input values).
CANONICAL_REPAIR_TEMPLATE: Dict[str, Any] = {
    "v2_meta": {
        "id": REPAIR_WORKFLOW_TEMPLATE_ID,
        "version": REPAIR_WORKFLOW_VERSION,
        "description": (
            "Bounded regional hand-repair inpaint pass. Reuses the primary SDXL "
            "checkpoint and LoRA; local hand/grip anatomy conditioning only; "
            "OpenPose ControlNet intentionally absent (single causal factor)."
        ),
        "openpose_controlnet_used": False,
        "whole_image_second_pass": False,
        "load_bearing": {
            "source_image": True,
            "repair_mask": True,
            "inpaint_conditioning": True,
        },
        "final_composite": "cpu_side_against_original_source",
    },
    "nodes": {
        "R0": {
            "class_type": REPAIR_NODE_CLASS_CHECKPOINT,
            "inputs": {"ckpt_name": "REPLACE_CHECKPOINT"},
        },
        "R1": {
            "class_type": REPAIR_NODE_CLASS_LORA,
            "inputs": {
                "lora_name": "REPLACE_LORA",
                "strength_model": "REPLACE_LORA_STRENGTH",
                "strength_clip": "REPLACE_LORA_STRENGTH",
                "model": ["R0", 0],
                "clip": ["R0", 1],
            },
        },
        "R2": {
            "class_type": REPAIR_NODE_CLASS_CLIPENC,
            "inputs": {"text": "REPLACE_POSITIVE", "clip": ["R1", 1]},
        },
        "R3": {
            "class_type": REPAIR_NODE_CLASS_CLIPENC,
            "inputs": {"text": "REPLACE_NEGATIVE", "clip": ["R1", 1]},
        },
        "R4": {
            "class_type": REPAIR_NODE_CLASS_LOADIMAGE,
            "inputs": {"image": "REPLACE_SOURCE_IMAGE"},
        },
        "R5": {
            "class_type": REPAIR_NODE_CLASS_LOADMASK,
            "inputs": {"image": "REPLACE_REPAIR_MASK", "channel": "red"},
        },
        "R6": {
            "class_type": REPAIR_NODE_CLASS_VAEENCODEINPAINT,
            "inputs": {
                "pixels": ["R4", 0],
                "vae": ["R0", 2],
                "mask": ["R5", 0],
                "grow_mask_by": 0,
            },
        },
        "R7": {
            "class_type": REPAIR_NODE_CLASS_KSAMPLER,
            "inputs": {
                "seed": "REPLACE_SEED",
                "steps": "REPLACE_STEPS",
                "cfg": "REPLACE_CFG",
                "sampler_name": "REPLACE_SAMPLER",
                "scheduler": "REPLACE_SCHEDULER",
                "denoise": "REPLACE_DENOISE",
                "model": ["R1", 0],
                "positive": ["R2", 0],
                "negative": ["R3", 0],
                "latent_image": ["R6", 0],
            },
        },
        "R8": {
            "class_type": REPAIR_NODE_CLASS_VAEDECODE,
            "inputs": {"samples": ["R7", 0], "vae": ["R0", 2]},
        },
        "R9": {
            "class_type": REPAIR_NODE_CLASS_SAVEIMAGE,
            "inputs": {"images": ["R8", 0], "filename_prefix": "REPLACE_OUTPUT_PREFIX"},
        },
    },
}


def _compute_template_hash(template_nodes: Dict[str, Any]) -> str:
    """Deterministic hash of the template node structure (no input values)."""
    structural = {}
    for node_id, node in sorted(template_nodes.items()):
        structural[node_id] = {
            "class_type": node["class_type"],
            "inputs": {
                k: v for k, v in sorted(node["inputs"].items())
                if not isinstance(v, str) or not v.startswith("REPLACE_")
            },
        }
    return hashlib.sha256(
        json.dumps(structural, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# Frozen template hash (computed once at module load).
FROZEN_TEMPLATE_HASH: str = _compute_template_hash(CANONICAL_REPAIR_TEMPLATE["nodes"])


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class WorkflowValidationError(Exception):
    """Raised when a workflow fails validation against the frozen contract."""


class UnknownNodeClassError(WorkflowValidationError):
    """An unknown node class was found."""


class MissingRequiredNodeError(WorkflowValidationError):
    """A required node class is missing."""


class ExceededNodeCountError(WorkflowValidationError):
    """Too many nodes of a given class."""


class TemplateHashMismatchError(WorkflowValidationError):
    """The workflow structure does not match the frozen template."""


class ProhibitedNodeError(WorkflowValidationError):
    """A prohibited node class was found."""


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Result of workflow validation."""
    valid: bool
    errors: Tuple[str, ...] = ()
    node_count: int = 0
    ksampler_count: int = 0
    saveimage_count: int = 0
    loadmask_count: int = 0
    template_hash: str = ""

    def raise_on_error(self) -> None:
        if not self.valid:
            raise WorkflowValidationError(
                f"workflow validation failed: {'; '.join(self.errors)}"
            )


def validate_workflow(workflow: Dict[str, Any]) -> ValidationResult:
    """Validate a workflow against the frozen repair contract.

    Checks:
        - All node classes are in the allowlist
        - All required node classes are present
        - KSampler count <= 1
        - SaveImage count <= 1
        - LoadImageMask count <= 1
        - No prohibited nodes (custom, shell, network, downloader)
    """
    errors: list[str] = []

    if not isinstance(workflow, dict):
        return ValidationResult(valid=False, errors=("workflow must be a dict",))

    nodes = workflow.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return ValidationResult(valid=False, errors=("workflow.nodes must be a non-empty dict",))

    # Count node classes
    class_counts: Dict[str, int] = {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            errors.append(f"node {node_id} is not a dict")
            continue
        class_type = node.get("class_type")
        if class_type is None:
            errors.append(f"node {node_id} missing class_type")
            continue
        if class_type not in ALLOWED_NODE_CLASSES:
            errors.append(
                f"node {node_id}: prohibited class {class_type!r} "
                f"(allowed: {sorted(ALLOWED_NODE_CLASSES)})"
            )
        class_counts[class_type] = class_counts.get(class_type, 0) + 1

    # Check required classes
    for required in REQUIRED_NODE_CLASSES:
        if class_counts.get(required, 0) == 0:
            errors.append(f"missing required node class: {required}")

    # Check counts
    ksampler_count = class_counts.get(REPAIR_NODE_CLASS_KSAMPLER, 0)
    if ksampler_count > MAX_KSAMPLER_COUNT:
        errors.append(
            f"too many KSampler nodes: {ksampler_count} > {MAX_KSAMPLER_COUNT}"
        )

    saveimage_count = class_counts.get(REPAIR_NODE_CLASS_SAVEIMAGE, 0)
    if saveimage_count > MAX_SAVEIMAGE_COUNT:
        errors.append(
            f"too many SaveImage nodes: {saveimage_count} > {MAX_SAVEIMAGE_COUNT}"
        )

    loadmask_count = class_counts.get(REPAIR_NODE_CLASS_LOADMASK, 0)
    if loadmask_count > MAX_LOADMASK_COUNT:
        errors.append(
            f"too many LoadImageMask nodes: {loadmask_count} > {MAX_LOADMASK_COUNT}"
        )

    # Compute template hash
    template_hash = _compute_template_hash(nodes) if not errors else ""

    valid = len(errors) == 0
    return ValidationResult(
        valid=valid,
        errors=tuple(errors),
        node_count=len(nodes),
        ksampler_count=ksampler_count,
        saveimage_count=saveimage_count,
        loadmask_count=loadmask_count,
        template_hash=template_hash,
    )


def validate_workflow_strict(workflow: Dict[str, Any]) -> ValidationResult:
    """Strict validation: also checks template hash matches frozen template."""
    result = validate_workflow(workflow)
    if not result.valid:
        return result

    if result.template_hash != FROZEN_TEMPLATE_HASH:
        return ValidationResult(
            valid=False,
            errors=(
                f"template hash mismatch: expected {FROZEN_TEMPLATE_HASH[:16]}..., "
                f"got {result.template_hash[:16]}...",
            ),
            node_count=result.node_count,
            ksampler_count=result.ksampler_count,
            saveimage_count=result.saveimage_count,
            loadmask_count=result.loadmask_count,
            template_hash=result.template_hash,
        )

    return result


# ---------------------------------------------------------------------------
# Template builder
# ---------------------------------------------------------------------------


def build_frozen_template() -> Dict[str, Any]:
    """Return a deep copy of the canonical repair template."""
    return copy.deepcopy(CANONICAL_REPAIR_TEMPLATE)


def get_frozen_template_hash() -> str:
    """Return the frozen template hash."""
    return FROZEN_TEMPLATE_HASH


def get_allowed_node_classes() -> FrozenSet[str]:
    """Return the frozen node allowlist."""
    return ALLOWED_NODE_CLASSES


def get_required_node_classes() -> FrozenSet[str]:
    """Return the frozen required node set."""
    return REQUIRED_NODE_CLASSES
