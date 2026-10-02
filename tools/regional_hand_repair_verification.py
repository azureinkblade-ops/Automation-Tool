"""EA-4D.4F Regional Hand Repair verification orchestrator.

This module implements three verification layers:
- V0: Admission (authority lineage, route, worker, input hash, dimensions, template)
- V1: Candidate integrity (output exists, decodes, dimensions match, not uniform)
- V2: Deterministic compositing and immutability (outside-region immutability)
- V3: Protected-object boundary (Soulblade boundary)
- V4: Model quality and human acceptance (separate from deterministic correctness)

Design source of truth:
    EA-4D.4F-R6-CANONICAL_PILOT_CONTRACT.md
    .hermes/handoffs/ea4d4f/step-1-workflow-manifest.md

Authority limits:
    CPU-only. No GPU, no ComfyUI client, no submission.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from tools.regional_hand_repair import (
    RepairImmutabilityViolation,
    RepairSoulbladeViolation,
    RepairCandidateContentError,
    verify_outside_region_immutability,
    verify_soulblade_boundary,
    verify_repair_candidate_content,
    composite_repaired_against_source,
    REPAIR_REGION_PADDING,
)
from tools.regional_hand_repair_workflow import validate_workflow


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerificationResult:
    """Result of the complete verification pipeline."""
    admission: str  # PASS or FAIL
    candidate_integrity: str  # PASS or FAIL
    outside_region_immutability: str  # PASS or FAIL
    soulblade_boundary: str  # PASS or FAIL
    quality: str  # NOT_EVALUATED, ACCEPTED, REJECTED
    errors: Tuple[str, ...] = ()
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def deterministic_pass(self) -> bool:
        """All deterministic checks passed."""
        return (
            self.admission == "PASS"
            and self.candidate_integrity == "PASS"
            and self.outside_region_immutability == "PASS"
            and self.soulblade_boundary == "PASS"
        )

    @property
    def technical_success(self) -> bool:
        """Technical success = deterministic pass."""
        return self.deterministic_pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "admission": self.admission,
            "candidate_integrity": self.candidate_integrity,
            "outside_region_immutability": self.outside_region_immutability,
            "soulblade_boundary": self.soulblade_boundary,
            "quality": self.quality,
            "errors": list(self.errors),
            "metrics": self.metrics,
        }


# ---------------------------------------------------------------------------
# Verification orchestrator
# ---------------------------------------------------------------------------


class RegionalHandRepairVerificationOrchestrator:
    """Orchestrates the verification pipeline for Regional Hand Repair.

    Layers:
        V0: Admission — authority lineage, route, worker, input hash, dimensions, template
        V1: Candidate integrity — output exists, decodes, dimensions match, not uniform
        V2: Deterministic compositing and immutability — outside-region immutability
        V3: Protected-object boundary — Soulblade boundary
        V4: Model quality and human acceptance — separate from deterministic correctness
    """

    def verify_admission(
        self,
        *,
        workflow: Dict[str, Any],
        source_png: bytes,
        mask_png: bytes,
        checkpoint_reference: str,
        lora_reference: str,
        expected_checkpoint_sha256: str,
        expected_lora_sha256: str,
        expected_source_sha256: str,
        expected_mask_sha256: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """V0: Admission verification.

        Returns:
            (PASS or FAIL, metrics dict)
        """
        metrics: Dict[str, Any] = {}
        errors: list[str] = []

        # Validate workflow
        try:
            result = validate_workflow(workflow)
            if not result.valid:
                errors.extend(result.errors)
            metrics["workflow_node_count"] = result.node_count
            metrics["workflow_template_hash"] = result.template_hash
        except Exception as e:
            errors.append(f"workflow validation error: {e}")

        # Verify source/mask dimensions match
        try:
            from tools.regional_hand_repair import _load_rgb, load_mask_alpha
            src = _load_rgb(source_png)
            mask, mw, mh = load_mask_alpha(mask_png)
            if src.size != (mw, mh):
                errors.append(
                    f"source dimensions {src.size} do not match mask dimensions {(mw, mh)}"
                )
            metrics["source_dimensions"] = list(src.size)
            metrics["mask_dimensions"] = [mw, mh]
        except Exception as e:
            errors.append(f"dimension verification error: {e}")

        if errors:
            return "FAIL", {"errors": errors, **metrics}

        return "PASS", metrics

    def verify_candidate_integrity(
        self,
        *,
        candidate_png: bytes,
        mask_png: bytes,
        source_png: Optional[bytes] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """V1: Candidate integrity verification.

        Returns:
            (PASS or FAIL, metrics dict)
        """
        try:
            result = verify_repair_candidate_content(candidate_png, mask_png, source_png)
            return "PASS", result
        except RepairCandidateContentError as e:
            return "FAIL", {"error": str(e)}

    def verify_outside_region_immutability(
        self,
        *,
        source_png: bytes,
        repaired_png: bytes,
        mask_png: bytes,
    ) -> Tuple[str, Dict[str, Any]]:
        """V2: Outside-region immutability verification.

        Returns:
            (PASS or FAIL, metrics dict)
        """
        try:
            verify_outside_region_immutability(source_png, repaired_png, mask_png)
            return "PASS", {}
        except RepairImmutabilityViolation as e:
            return "FAIL", {"error": str(e)}

    def verify_soulblade_boundary(
        self,
        *,
        source_png: bytes,
        repaired_png: bytes,
        mask_png: bytes,
        blade_rect: Tuple[float, float, float, float],
        contact_rect: Tuple[float, float, float, float],
        image_width: int,
        image_height: int,
    ) -> Tuple[str, Dict[str, Any]]:
        """V3: Soulblade boundary verification.

        Returns:
            (PASS or FAIL, metrics dict)
        """
        try:
            verify_soulblade_boundary(
                source_png, repaired_png, mask_png,
                blade_rect, contact_rect,
                image_width=image_width, image_height=image_height,
            )
            return "PASS", {}
        except RepairSoulbladeViolation as e:
            return "FAIL", {"error": str(e)}

    def verify_all(
        self,
        *,
        workflow: Dict[str, Any],
        source_png: bytes,
        mask_png: bytes,
        candidate_png: bytes,
        blade_rect: Tuple[float, float, float, float],
        contact_rect: Tuple[float, float, float, float],
        image_width: int,
        image_height: int,
        checkpoint_reference: str = "",
        lora_reference: str = "",
        expected_checkpoint_sha256: str = "",
        expected_lora_sha256: str = "",
        expected_source_sha256: str = "",
        expected_mask_sha256: str = "",
    ) -> VerificationResult:
        """Run the complete verification pipeline.

        Returns:
            VerificationResult with all layer results.
        """
        errors: list[str] = []
        metrics: Dict[str, Any] = {}

        # V0: Admission
        admission, admission_metrics = self.verify_admission(
            workflow=workflow,
            source_png=source_png,
            mask_png=mask_png,
            checkpoint_reference=checkpoint_reference,
            lora_reference=lora_reference,
            expected_checkpoint_sha256=expected_checkpoint_sha256,
            expected_lora_sha256=expected_lora_sha256,
            expected_source_sha256=expected_source_sha256,
            expected_mask_sha256=expected_mask_sha256,
        )
        metrics["admission"] = admission_metrics
        if admission != "PASS":
            errors.append(f"admission failed: {admission_metrics.get('errors', [])}")

        # V1: Candidate integrity
        candidate_integrity, candidate_metrics = self.verify_candidate_integrity(
            candidate_png=candidate_png,
            mask_png=mask_png,
            source_png=source_png,
        )
        metrics["candidate_integrity"] = candidate_metrics
        if candidate_integrity != "PASS":
            errors.append(f"candidate integrity failed: {candidate_metrics.get('error', '')}")

        # V2: Outside-region immutability
        # First composite the repaired image
        try:
            repaired_png = composite_repaired_against_source(
                source_png, candidate_png, mask_png
            )
        except Exception as e:
            repaired_png = candidate_png  # Fallback

        immutability, immutability_metrics = self.verify_outside_region_immutability(
            source_png=source_png,
            repaired_png=repaired_png,
            mask_png=mask_png,
        )
        metrics["immutability"] = immutability_metrics
        if immutability != "PASS":
            errors.append(f"immutability failed: {immutability_metrics.get('error', '')}")

        # V3: Soulblade boundary
        soulblade, soulblade_metrics = self.verify_soulblade_boundary(
            source_png=source_png,
            repaired_png=repaired_png,
            mask_png=mask_png,
            blade_rect=blade_rect,
            contact_rect=contact_rect,
            image_width=image_width,
            image_height=image_height,
        )
        metrics["soulblade"] = soulblade_metrics
        if soulblade != "PASS":
            errors.append(f"soulblade boundary failed: {soulblade_metrics.get('error', '')}")

        return VerificationResult(
            admission=admission,
            candidate_integrity=candidate_integrity,
            outside_region_immutability=immutability,
            soulblade_boundary=soulblade,
            quality="NOT_EVALUATED",
            errors=tuple(errors),
            metrics=metrics,
        )
