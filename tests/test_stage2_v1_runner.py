from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.render_ab.run_stage2_v1 import validate_approval


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text('{"cases": []}', encoding="utf-8")
    return path


def test_gpu_execution_rejects_missing_explicit_approval_record(tmp_path):
    manifest = _manifest(tmp_path)

    with pytest.raises(ValueError, match="explicit GPU approval record is missing"):
        validate_approval(tmp_path / "missing.json", manifest)


def test_gpu_execution_rejects_approval_for_different_manifest(tmp_path):
    manifest = _manifest(tmp_path)
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "approved": True,
        "scope": "stage2-v1-gpu-execution",
        "manifest_sha256": "0" * 64,
        "approval_text": "Approved",
        "approved_at": "2026-07-26T18:30:00-07:00",
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="GPU approval manifest hash mismatch"):
        validate_approval(approval, manifest)


def test_gpu_execution_accepts_manifest_bound_explicit_approval(tmp_path):
    manifest = _manifest(tmp_path)
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "approved": True,
        "scope": "stage2-v1-gpu-execution",
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "approval_text": "Approve the frozen V1 GPU execution.",
        "approved_at": "2026-07-26T18:30:00-07:00",
    }), encoding="utf-8")

    payload = validate_approval(approval, manifest)

    assert payload["approved"] is True
    assert payload["scope"] == "stage2-v1-gpu-execution"
