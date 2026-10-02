"""CPU tests for hand_repair.mask_stub."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from hand_repair.mask_stub import generate_hand_mask, ensure_mask_for_source


def test_generate_hand_mask_dimensions(tmp_path: Path):
    src = tmp_path / "src.png"
    Image.new("RGB", (64, 128), (10, 20, 30)).save(src)
    out = tmp_path / "mask.png"
    generate_hand_mask(src, out, region="hands")
    mask = Image.open(out)
    assert mask.size == (64, 128)
    assert mask.mode == "L"
    # some white pixels
    assert max(mask.getdata()) > 0
    # some black pixels (border / upper area)
    assert min(mask.getdata()) == 0


def test_ensure_mask_reuses_existing(tmp_path: Path):
    src = tmp_path / "src.png"
    Image.new("RGB", (32, 32), (1, 1, 1)).save(src)
    existing = tmp_path / "given.png"
    Image.new("L", (32, 32), 128).save(existing)
    got = ensure_mask_for_source(src, tmp_path / "work", mask_path=existing)
    assert got == existing
