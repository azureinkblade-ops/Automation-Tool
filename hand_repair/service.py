"""Hand Repair Service - public API for regional hand repair.

This module is the only intended entry point for hand repair. It sits on top of
object_refinement.ObjectRefinementService and must remain free of app.py and
Streamlit/HTTP concerns.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from object_refinement import (
    AcceptanceVerdict,
    ObjectRefinementService,
    RefinementRequest,
    RefinementResult,
)

from .prompts import get_hand_negative, get_hand_prompt


def _flag_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class HandRepairRequest:
    source_path: Path
    region: str = "hands"  # "hands" | "left_hand" | "right_hand" | "both"
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    strength: float = 0.25
    seed: Optional[int] = None
    mask_path: Optional[Path] = None
    guide_path: Optional[Path] = None


@dataclass(frozen=True)
class HandRepairResult:
    status: str  # accepted | rejected | pending_review | disabled | error
    output_path: Path
    candidate_path: Optional[Path] = None
    provenance_path: Optional[Path] = None
    diff_path: Optional[Path] = None
    reasons: Tuple[str, ...] = ()


def _to_hand_result(ref: RefinementResult) -> HandRepairResult:
    reasons: Tuple[str, ...] = ()
    if ref.verdict is not None:
        reasons = tuple(ref.verdict.reasons)
    return HandRepairResult(
        status=ref.status,
        output_path=ref.output_path,
        candidate_path=ref.candidate_path,
        provenance_path=ref.provenance_path,
        diff_path=ref.diff_path,
        reasons=reasons,
    )


def repair_hands(
    request: HandRepairRequest,
    work_dir: Path,
    *,
    backend=None,
    reviewer=None,
) -> HandRepairResult:
    """Public entry point for hand repair.

    - Feature-flagged via HAND_REPAIR_ENABLED (default off).
    - Never raises for normal reject / disabled paths.
    - Preserves the outside-mask gate from object_refinement.
    """
    source = Path(request.source_path)
    work_dir = Path(work_dir)

    if not _flag_enabled("HAND_REPAIR_ENABLED", "0"):
        return HandRepairResult(
            status="disabled",
            output_path=source,
            reasons=("HAND_REPAIR_ENABLED is off",),
        )

    if not source.exists():
        return HandRepairResult(
            status="error",
            output_path=source,
            reasons=(f"source image not found: {source}",),
        )

    if request.mask_path is None or not Path(request.mask_path).exists():
        # Early versions require an explicit mask. Future slices may add a
        # coarse hand detector. For now we refuse to invent a mask.
        return HandRepairResult(
            status="rejected",
            output_path=source,
            reasons=("mask_path is required for hand repair in EA4F-1",),
        )

    prompt = get_hand_prompt(request.region, request.prompt)
    _ = get_hand_negative(request.negative_prompt)

    refinement_request = RefinementRequest(
        object_type="hand",
        target_region=request.region,
        prompt=prompt,
        mask_path=Path(request.mask_path),
        guide_path=Path(request.guide_path) if request.guide_path else None,
    )

    try:
        service = ObjectRefinementService(backend=backend, reviewer=reviewer)
        result = service.refine(
            source_path=source,
            request=refinement_request,
            work_dir=work_dir,
        )
        return _to_hand_result(result)
    except Exception as exc:  # pragma: no cover
        return HandRepairResult(
            status="error",
            output_path=source,
            reasons=(f"hand repair failed: {type(exc).__name__}: {exc}",),
        )
