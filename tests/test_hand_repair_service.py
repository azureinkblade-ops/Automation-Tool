"""Unit tests for hand_repair.service.

These tests do not require GPU or torch. They exercise the feature flag,
missing-mask path, and the public contract.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from hand_repair import HandRepairRequest, repair_hands
from hand_repair.prompts import get_hand_prompt, get_hand_negative


@pytest.fixture()
def tiny_rgb(tmp_path: Path) -> Path:
    path = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color=(120, 80, 60)).save(path)
    return path


@pytest.fixture()
def tiny_mask(tmp_path: Path) -> Path:
    path = tmp_path / "mask.png"
    # mostly black with a small white region so it is a valid mask
    img = Image.new("L", (64, 64), color=0)
    for x in range(20, 40):
        for y in range(20, 40):
            img.putpixel((x, y), 255)
    img.save(path)
    return path


def test_disabled_by_default(tiny_rgb: Path, tmp_path: Path):
    # Ensure flag is off
    os.environ.pop("HAND_REPAIR_ENABLED", None)
    result = repair_hands(
        HandRepairRequest(source_path=tiny_rgb, mask_path=tmp_path / "missing.png"),
        work_dir=tmp_path / "work",
    )
    assert result.status == "disabled"
    assert result.output_path == tiny_rgb
    assert "HAND_REPAIR_ENABLED is off" in result.reasons


def test_missing_mask_rejected_when_enabled(tiny_rgb: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HAND_REPAIR_ENABLED", "1")
    result = repair_hands(
        HandRepairRequest(source_path=tiny_rgb, mask_path=None),
        work_dir=tmp_path / "work",
    )
    assert result.status == "rejected"
    assert result.output_path == tiny_rgb
    assert any("mask_path is required" in r for r in result.reasons)


def test_missing_source_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HAND_REPAIR_ENABLED", "1")
    missing = tmp_path / "does-not-exist.png"
    result = repair_hands(
        HandRepairRequest(source_path=missing, mask_path=tmp_path / "m.png"),
        work_dir=tmp_path / "work",
    )
    assert result.status == "error"
    assert any("not found" in r for r in result.reasons)


def test_default_prompt_bank():
    assert "anatomically correct" in get_hand_prompt("hands")
    assert "five fingers" in get_hand_prompt("left_hand")
    assert "extra fingers" in get_hand_negative()
    assert get_hand_prompt("hands", override="custom prompt") == "custom prompt"


def test_public_exports():
    from hand_repair import HandRepairRequest, HandRepairResult, repair_hands
    assert callable(repair_hands)
    assert HandRepairRequest is not None
    assert HandRepairResult is not None


def test_auto_mask_when_enabled(tiny_rgb, tmp_path, monkeypatch):
    monkeypatch.setenv("HAND_REPAIR_ENABLED", "1")
    monkeypatch.setenv("HAND_REPAIR_AUTO_MASK", "1")
    # Without a real backend the refine path may error after mask; we only
    # assert we no longer reject solely for missing mask before backend.
    result = repair_hands(
        HandRepairRequest(source_path=tiny_rgb, mask_path=None),
        work_dir=tmp_path / "work",
    )
    # disabled path for VISUAL_OBJECT_REFINEMENT or error/pending - not "mask required"
    assert not any("mask_path is required" in r for r in result.reasons)
    assert result.status in {"disabled", "pending_review", "rejected", "error", "accepted"}
