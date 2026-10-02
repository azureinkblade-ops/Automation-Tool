"""Canonical task-input identity for the bounded regional hand-repair pilot."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Dict, Optional

from tools.regional_hand_repair import (
    OPENPOSE_CONTROLNET_USED_IN_REPAIR,
    REGIONAL_HAND_REPAIR_STAGE,
    REGIONAL_HAND_REPAIR_VERSION,
    RepairIdentityError,
    RepairRequest,
    conditioning_sha256,
)

CANONICAL_SCHEMA_VERSION = "1.0"
WORKFLOW_TEMPLATE_ID = "regional-hand-repair-inpaint"
WORKFLOW_TEMPLATE_VERSION = "1.0"
MASK_SEMANTICS = "alpha_gt_zero_is_mutable"
HAND_GUIDE_ROLE = "openpose_21_hand"

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EIGHT_PLACES = Decimal("0.00000001")


def _sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RepairIdentityError(f"{label} must be 64 hexadecimal characters")
    return value.lower()


def _decimal8(value: Any, label: str) -> str:
    try:
        decimal_value = Decimal(str(value)).quantize(
            _EIGHT_PLACES, rounding=ROUND_HALF_EVEN
        )
    except (InvalidOperation, ValueError) as exc:
        raise RepairIdentityError(f"{label} must be a finite decimal") from exc
    if not decimal_value.is_finite():
        raise RepairIdentityError(f"{label} must be a finite decimal")
    return format(decimal_value, ".8f")


def _optional_lora(request: RepairRequest) -> Optional[Dict[str, Any]]:
    if not request.lora_asset_id:
        return None
    return {
        "asset_id": request.lora_asset_id,
        "reference": request.lora_reference or None,
        "sha256": _sha256(request.lora_sha256, "lora.sha256"),
        "strength": _decimal8(request.lora_strength, "lora.strength"),
    }


def build_canonical_task_input_envelope(
    request: RepairRequest,
    *,
    source_width: int,
    source_height: int,
    workflow_template_sha256: str,
    allowed_node_set_sha256: str,
    source_color_mode: str = "RGB",
    source_opaque: bool = True,
    ip_adapter: Optional[Dict[str, Any]] = None,
    controlnet: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the path-independent execution-material envelope from the contract."""
    if source_width <= 0 or source_height <= 0:
        raise RepairIdentityError("source dimensions must be positive integers")
    if source_color_mode != "RGB" or source_opaque is not True:
        raise RepairIdentityError("pilot source must be opaque RGB")
    if OPENPOSE_CONTROLNET_USED_IN_REPAIR:
        raise RepairIdentityError("pilot repair must not enable OpenPose ControlNet")

    region = request.repair_region
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "stage": REGIONAL_HAND_REPAIR_STAGE,
        "stage_version": REGIONAL_HAND_REPAIR_VERSION,
        "source_image": {
            "sha256": _sha256(request.source_image_sha256, "source_image.sha256"),
            "width": int(source_width),
            "height": int(source_height),
            "color_mode": source_color_mode,
            "opaque": True,
        },
        "hand_guide": {
            "sha256": _sha256(request.hand_guide_sha256, "hand_guide.sha256"),
            "role": HAND_GUIDE_ROLE,
            "structural_request_sha256": _sha256(
                request.structural_request_sha256,
                "hand_guide.structural_request_sha256",
            ),
        },
        "repair_region": {
            "algorithm_version": REGIONAL_HAND_REPAIR_VERSION,
            "region_sha256": _sha256(region.sha256(), "repair_region.region_sha256"),
            "rect_normalized": [
                _decimal8(value, "repair_region.rect_normalized")
                for value in region.rect()
            ],
            "padding_normalized": _decimal8(
                region.padding, "repair_region.padding_normalized"
            ),
            "mask_sha256": _sha256(
                request.repair_mask_sha256, "repair_region.mask_sha256"
            ),
            "mask_semantics": MASK_SEMANTICS,
            "feather_px": int(request.feather_px),
        },
        "conditioning": {
            "positive_prompt_sha256": conditioning_sha256(request.repair_prompt),
            "negative_prompt_sha256": conditioning_sha256(
                request.repair_negative_prompt
            ),
        },
        "sampling": {
            "seed": int(request.repair_seed),
            "sampler": request.sampler,
            "scheduler": request.scheduler,
            "steps": int(request.steps),
            "cfg": _decimal8(request.cfg, "sampling.cfg"),
            "denoise": _decimal8(request.denoise, "sampling.denoise"),
        },
        "checkpoint": {
            "asset_id": request.checkpoint_asset_id,
            "reference": request.checkpoint_reference,
            "sha256": _sha256(request.checkpoint_sha256, "checkpoint.sha256"),
        },
        "lora": _optional_lora(request),
        "ip_adapter": ip_adapter,
        "controlnet": controlnet,
        "workflow": {
            "template_id": WORKFLOW_TEMPLATE_ID,
            "template_version": WORKFLOW_TEMPLATE_VERSION,
            "template_sha256": _sha256(
                workflow_template_sha256, "workflow.template_sha256"
            ),
            "allowed_node_set_sha256": _sha256(
                allowed_node_set_sha256, "workflow.allowed_node_set_sha256"
            ),
        },
    }


def canonical_json_bytes(envelope: Dict[str, Any]) -> bytes:
    return json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def canonical_task_input_sha256(envelope: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
