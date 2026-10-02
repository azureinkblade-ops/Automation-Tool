"""Tests for EA-4D.4F Regional Hand Repair verification orchestrator."""

import pytest
from PIL import Image
import io

from tools.regional_hand_repair_verification import (
    VerificationResult,
    RegionalHandRepairVerificationOrchestrator,
)
from tools.regional_hand_repair_workflow import build_frozen_template


def _create_test_image(width: int, height: int, color: tuple = (128, 128, 128)) -> bytes:
    """Create a test PNG image."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_test_mask(width: int, height: int, mask_region: tuple = None) -> bytes:
    """Create a test mask PNG image."""
    img = Image.new("L", (width, height), 0)
    if mask_region:
        x, y, w, h = mask_region
        for py in range(y, min(y + h, height)):
            for px in range(x, min(x + w, width)):
                img.putpixel((px, py), 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def orchestrator():
    return RegionalHandRepairVerificationOrchestrator()


class TestVerificationResult:
    def test_technical_success_all_pass(self):
        result = VerificationResult(
            admission="PASS",
            candidate_integrity="PASS",
            outside_region_immutability="PASS",
            soulblade_boundary="PASS",
            quality="NOT_EVALUATED",
        )
        assert result.technical_success

    def test_technical_success_one_fail(self):
        result = VerificationResult(
            admission="PASS",
            candidate_integrity="FAIL",
            outside_region_immutability="PASS",
            soulblade_boundary="PASS",
            quality="NOT_EVALUATED",
        )
        assert not result.technical_success

    def test_to_dict(self):
        result = VerificationResult(
            admission="PASS",
            candidate_integrity="PASS",
            outside_region_immutability="PASS",
            soulblade_boundary="PASS",
            quality="ACCEPTED",
        )
        d = result.to_dict()
        assert d["admission"] == "PASS"
        assert d["quality"] == "ACCEPTED"


class TestAdmission:
    def test_valid_admission(self, orchestrator):
        workflow = build_frozen_template()
        source = _create_test_image(64, 64)
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        result, metrics = orchestrator.verify_admission(
            workflow=workflow,
            source_png=source,
            mask_png=mask,
            checkpoint_reference="test.ckpt",
            lora_reference="test.safetensors",
            expected_checkpoint_sha256="a" * 64,
            expected_lora_sha256="b" * 64,
            expected_source_sha256="c" * 64,
            expected_mask_sha256="d" * 64,
        )
        assert result == "PASS"


class TestCandidateIntegrity:
    def test_valid_candidate(self, orchestrator):
        source = _create_test_image(64, 64)
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        # Create candidate with strong chromatic variation (high contrast)
        img = Image.new("RGB", (64, 64))
        for y in range(64):
            for x in range(64):
                # High-contrast pattern that exceeds structural variance threshold
                r = 255 if (x + y) % 2 == 0 else 0
                g = 255 if (x * 3 + y) % 3 == 0 else 0
                b = 255 if (x + y * 3) % 4 == 0 else 0
                img.putpixel((x, y), (r, g, b))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        candidate = buf.getvalue()
        result, metrics = orchestrator.verify_candidate_integrity(
            candidate_png=candidate,
            mask_png=mask,
            source_png=source,
        )
        assert result == "PASS"

    def test_candidate_wrong_size(self, orchestrator):
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        candidate = _create_test_image(32, 32)
        result, metrics = orchestrator.verify_candidate_integrity(
            candidate_png=candidate,
            mask_png=mask,
        )
        assert result == "FAIL"


class TestOutsideRegionImmutability:
    def test_identical_images_pass(self, orchestrator):
        source = _create_test_image(64, 64)
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        result, metrics = orchestrator.verify_outside_region_immutability(
            source_png=source,
            repaired_png=source,
            mask_png=mask,
        )
        assert result == "PASS"

    def test_outside_pixel_changed_fails(self, orchestrator):
        source = _create_test_image(64, 64, (100, 100, 100))
        repaired = _create_test_image(64, 64, (100, 100, 100))
        # Change a pixel outside the mask
        repaired_img = Image.open(io.BytesIO(repaired))
        repaired_img.putpixel((0, 0), (200, 200, 200))
        buf = io.BytesIO()
        repaired_img.save(buf, format="PNG")
        repaired = buf.getvalue()
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        result, metrics = orchestrator.verify_outside_region_immutability(
            source_png=source,
            repaired_png=repaired,
            mask_png=mask,
        )
        assert result == "FAIL"


class TestSoulbladeBoundary:
    def test_no_blade_change_passes(self, orchestrator):
        source = _create_test_image(64, 64)
        repaired = source
        mask = _create_test_mask(64, 64, (16, 16, 32, 32))
        result, metrics = orchestrator.verify_soulblade_boundary(
            source_png=source,
            repaired_png=repaired,
            mask_png=mask,
            blade_rect=(0.25, 0.25, 0.5, 0.5),
            contact_rect=(0.3, 0.3, 0.4, 0.4),
            image_width=64,
            image_height=64,
        )
        assert result == "PASS"
