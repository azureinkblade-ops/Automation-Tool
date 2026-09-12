"""Frozen workflow boundary for the regional hand-repair pilot.

This module is CPU-only. It validates the deterministic workflow produced by
``regional_hand_repair`` against the exact node IDs and class types authorized
for the pilot. It does not construct a client, access the filesystem, or submit
work to ComfyUI.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from tools.regional_hand_repair import (
    REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT,
    REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK,
    REPAIR_WORKFLOW_TEMPLATE_ID,
    REPAIR_WORKFLOW_VERSION,
)


class RegionalHandRepairWorkflowContractError(ValueError):
    """The workflow differs from the frozen pilot capability."""


_CONTROL_NODES = {
    "R0": "CheckpointLoaderSimple",
    "R1": "LoraLoader",
    "R2": "CLIPTextEncode",
    "R3": "CLIPTextEncode",
    "R4": "LoadImage",
    "R5": "LoadImageMask",
    "R6": "VAEEncodeForInpaint",
    "R7": "KSampler",
    "R8": "VAEDecode",
    "R9": "SaveImage",
}

_TREATMENT_NODES = {
    "R0": "CheckpointLoaderSimple",
    "R1": "LoraLoader",
    "R2": "CLIPTextEncode",
    "R3": "CLIPTextEncode",
    "R4": "LoadImage",
    "R5": "LoadImageMask",
    "R6T": "VAEEncode",
    "R6M": "SetLatentNoiseMask",
    "R7": "KSampler",
    "R8": "VAEDecode",
    "R9": "SaveImage",
}


def canonical_workflow_bytes(workflow: Mapping[str, Any]) -> bytes:
    return json.dumps(
        workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def workflow_sha256(workflow: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_workflow_bytes(workflow)).hexdigest()


def frozen_node_allowlist(encode_architecture: str) -> dict[str, str]:
    if encode_architecture == REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_FOR_INPAINT:
        return dict(_CONTROL_NODES)
    if (
        encode_architecture
        == REPAIR_ENCODE_ARCHITECTURE_VAEENCODE_SET_LATENT_NOISE_MASK
    ):
        return dict(_TREATMENT_NODES)
    raise RegionalHandRepairWorkflowContractError(
        f"unsupported repair encode architecture: {encode_architecture!r}"
    )


def validate_frozen_repair_workflow(workflow: Mapping[str, Any]) -> str:
    """Validate exact template identity and node topology, returning its hash."""
    if not isinstance(workflow, Mapping):
        raise RegionalHandRepairWorkflowContractError("workflow must be a mapping")
    meta = workflow.get("v2_meta")
    nodes = workflow.get("nodes")
    if not isinstance(meta, Mapping) or not isinstance(nodes, Mapping):
        raise RegionalHandRepairWorkflowContractError(
            "workflow requires v2_meta and nodes mappings"
        )
    if meta.get("id") != REPAIR_WORKFLOW_TEMPLATE_ID:
        raise RegionalHandRepairWorkflowContractError("template id is not allowlisted")
    if meta.get("version") != REPAIR_WORKFLOW_VERSION:
        raise RegionalHandRepairWorkflowContractError(
            "template version is not allowlisted"
        )
    if meta.get("openpose_controlnet_used") is not False:
        raise RegionalHandRepairWorkflowContractError(
            "repair OpenPose ControlNet is prohibited"
        )
    if meta.get("whole_image_second_pass") is not False:
        raise RegionalHandRepairWorkflowContractError(
            "whole-image second pass is prohibited"
        )
    expected = frozen_node_allowlist(str(meta.get("encode_architecture", "")))
    actual = {
        str(node_id): str(node.get("class_type", ""))
        for node_id, node in nodes.items()
        if isinstance(node, Mapping)
    }
    if actual != expected or len(actual) != len(nodes):
        raise RegionalHandRepairWorkflowContractError(
            f"workflow node allowlist mismatch: expected {expected!r}, got {actual!r}"
        )
    return workflow_sha256(workflow)
