"""Coarse hand-region mask stub for EA4F-1 pilot.

Not a full hand detector. Produces a deterministic L-mode mask for experiments
and for HAND_REPAIR_MASK_PATH when auto-mask is enabled. Replace later with a
real detector without changing the HandRepairService contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Tuple

Region = Literal["hands", "left_hand", "right_hand", "both", "lower_third"]


def _box_for_region(width: int, height: int, region: str) -> Tuple[int, int, int, int]:
    """Return (x0, y0, x1, y1) in pixel coords for a coarse authorized region."""
    region = (region or "hands").lower()
    if region in {"lower_third", "hands", "both"}:
        # Lower third of frame (typical hand placement in vertical promos)
        y0 = int(height * 0.55)
        return 0, y0, width, height
    if region == "left_hand":
        return 0, int(height * 0.45), int(width * 0.55), height
    if region == "right_hand":
        return int(width * 0.45), int(height * 0.45), width, height
    # default
    y0 = int(height * 0.55)
    return 0, y0, width, height


def generate_hand_mask(
    source_path: Path,
    output_path: Path,
    *,
    region: str = "hands",
    soft_edge: int = 8,
) -> Path:
    """Write a white-on-black L mask for the coarse region. Returns output_path.

    soft_edge: approximate feather radius in pixels (box blur iterations).
    """
    from PIL import Image, ImageDraw, ImageFilter

    source_path = Path(source_path)
    output_path = Path(output_path)
    img = Image.open(source_path).convert("RGB")
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = _box_for_region(w, h, region)
    # Inset slightly so outside-mask gate has clear black border
    pad = max(2, min(w, h) // 64)
    draw.rectangle([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=255)
    if soft_edge and soft_edge > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=min(soft_edge, 32)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(output_path)
    return output_path


def ensure_mask_for_source(
    source_path: Path,
    work_dir: Path,
    *,
    region: str = "hands",
    mask_path: Path | None = None,
) -> Path:
    """Return an existing mask_path, or generate a stub mask under work_dir."""
    if mask_path is not None and Path(mask_path).exists():
        return Path(mask_path)
    out = Path(work_dir) / f"mask_stub_{region}.png"
    return generate_hand_mask(source_path, out, region=region)
