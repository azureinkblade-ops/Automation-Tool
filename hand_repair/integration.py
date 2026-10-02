"""Thin integration helpers for wiring hand repair into the promo pipeline.

This module is the only place that knows how the service is invoked from the
app shell. Keep call sites tiny: import one function, pass paths, respect flags.

Example app.py wiring (after main image is written to `image_path`):

    from hand_repair.integration import maybe_repair_hands

    image_path = maybe_repair_hands(
        source_path=image_path,
        work_dir=campaign_dir / "hand-repair",
        mask_path=optional_mask_path,  # required in EA4F-1
        region="hands",
    )
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .service import HandRepairRequest, HandRepairResult, repair_hands


def maybe_repair_hands(
    source_path: Path,
    work_dir: Path,
    *,
    mask_path: Optional[Path] = None,
    region: str = "hands",
    prompt: Optional[str] = None,
    guide_path: Optional[Path] = None,
    backend=None,
    reviewer=None,
) -> Path:
    """Run hand repair when enabled; always return a usable image path.

    Returns the repaired path on accept, otherwise the original source path.
    Never raises for normal disabled/reject paths.
    """
    result = repair_hands(
        HandRepairRequest(
            source_path=Path(source_path),
            region=region,
            prompt=prompt,
            mask_path=Path(mask_path) if mask_path else None,
            guide_path=Path(guide_path) if guide_path else None,
        ),
        work_dir=Path(work_dir),
        backend=backend,
        reviewer=reviewer,
    )
    return Path(result.output_path)


def repair_hands_detailed(
    source_path: Path,
    work_dir: Path,
    **kwargs,
) -> HandRepairResult:
    """Same as maybe_repair_hands but returns the full HandRepairResult."""
    mask_path = kwargs.pop("mask_path", None)
    return repair_hands(
        HandRepairRequest(
            source_path=Path(source_path),
            mask_path=Path(mask_path) if mask_path else None,
            **{k: v for k, v in kwargs.items() if k in {
                "region", "prompt", "negative_prompt", "strength", "seed", "guide_path"
            }},
        ),
        work_dir=Path(work_dir),
        backend=kwargs.get("backend"),
        reviewer=kwargs.get("reviewer"),
    )
