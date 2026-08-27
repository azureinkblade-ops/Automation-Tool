"""EA-4D.4F source-freeze integrity guard."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace
from pathlib import Path

from tools.regional_hand_repair_workflow import get_frozen_template_hash
from tests.test_regional_hand_repair_contract import repair_request


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".hermes" / "handoffs" / "ea4d4f" / "source-freeze-manifest.json"
FORBIDDEN_SUFFIXES = {
    ".ckpt", ".db", ".jpeg", ".jpg", ".onnx", ".png", ".pt", ".pth",
    ".safetensors", ".sqlite", ".tmp",
}


def test_source_freeze_hashes_and_artifact_boundary():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 44
    for relative_path, expected_sha256 in manifest["files"].items():
        path = ROOT / relative_path
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_sha256, relative_path
        assert path.suffix.lower() not in FORBIDDEN_SUFFIXES, relative_path
        assert len(payload) < 1_000_000, relative_path
    assert get_frozen_template_hash() == manifest["workflowTemplateHash"]


def test_source_freeze_imports_without_host_path_setup():
    modules = (
        "tools.regional_hand_repair",
        "tools.regional_hand_repair_adapter",
        "tools.regional_hand_repair_cleanup",
        "tools.regional_hand_repair_contract",
        "tools.regional_hand_repair_evidence",
        "tools.regional_hand_repair_failures",
        "tools.regional_hand_repair_pilot",
        "tools.regional_hand_repair_submission",
        "tools.regional_hand_repair_verification",
        "tools.regional_hand_repair_workflow",
        "tools.regional_hand_repair_workflow_contract",
        "tools.hermes_core.regional_hand_repair_evidence_store",
        "tools.hermes_core.regional_hand_repair_runtime_adapter",
    )
    for module in modules:
        assert importlib.import_module(module) is not None


def test_host_io_paths_are_excluded_from_canonical_identity(repair_request):
    left = replace(
        repair_request,
        source_image_path=r"C:\host-a\input.png",
        hand_guide_reference=r"C:\host-a\guide.png",
    )
    right = replace(
        repair_request,
        source_image_path="/mnt/host-b/input.png",
        hand_guide_reference="/mnt/host-b/guide.png",
    )

    assert left.identity_payload() != right.identity_payload()
    assert left.hash_preimage() == right.hash_preimage()
    assert left.sha256() == right.sha256()
    assert "source_image_path" not in left.hash_preimage()
    assert "hand_guide_reference" not in left.hash_preimage()
