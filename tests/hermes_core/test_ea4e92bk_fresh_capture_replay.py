"""Synthetic, offline fixtures only. No receiver or provider execution."""

from dataclasses import replace
import hashlib
import json

import pytest

from tools.ea4e92bk_fresh_capture_replay import (
    FreshCaptureExpectation, FreshCaptureReplayError, verify_fresh_capture,
)
from tools.hermes_core.hashing import sha256_payload


TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
TEXT = "EA4E92_OPENCODE_CURRENT_REPLAY_OK"


def _fixture(root):
    expected = FreshCaptureExpectation(
        run_id="run-1", attempt_id="attempt-1", authorization_id="auth-1",
        source_commit="a" * 40, executable_sha256="b" * 64,
        config_sha256="c" * 64, transport_id="d" * 64,
        model_binding_id="e" * 64, task=TASK, expected_text=TEXT,
        manifest_sha256="",
    )
    stdout = json.dumps({"type": "text", "text": TEXT}).encode() + b"\n"
    stderr = b""
    (root / "request.bin").write_bytes(TASK)
    (root / "stdout.jsonl").write_bytes(stdout)
    (root / "stderr.bin").write_bytes(stderr)
    manifest = {
        "schema_version": 1,
        "capture_class": "FRESH_CURRENT_QUALIFICATION",
        "historical_capture": False,
        "receiver_id": "opencode-cli-agent",
        "run_id": expected.run_id,
        "attempt_id": expected.attempt_id,
        "authorization_id": expected.authorization_id,
        "source_commit": expected.source_commit,
        "executable_sha256": expected.executable_sha256,
        "config_sha256": expected.config_sha256,
        "transport_id": expected.transport_id,
        "model_binding_id": expected.model_binding_id,
        "task_sha256": hashlib.sha256(TASK).hexdigest(),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_total_bytes": len(stdout),
        "stderr_total_bytes": len(stderr),
        "started_at_utc": "2026-09-29T12:00:00Z",
        "ended_at_utc": "2026-09-29T12:00:01Z",
        "pid": 12345,
        "exit_code": 0,
        "timed_out": False,
        "cancelled": False,
        "stdout_complete": True,
        "stderr_complete": True,
        "cleanup_confirmed": True,
        "process_start_count": 1,
        "provider_call_count": 1,
    }
    return replace(expected, manifest_sha256=_save(root, manifest)), manifest


def _save(root, manifest):
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    payload["manifest_sha256"] = sha256_payload(payload)
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload["manifest_sha256"]


def test_synthetic_fresh_capture_replays_with_production_parser(tmp_path):
    expected, _ = _fixture(tmp_path)
    assert verify_fresh_capture(tmp_path, expected) == TEXT


@pytest.mark.parametrize("field", [
    "run_id", "attempt_id", "authorization_id", "source_commit",
    "executable_sha256", "config_sha256", "transport_id", "model_binding_id",
])
def test_wrong_expected_identity_denied(tmp_path, field):
    expected, _ = _fixture(tmp_path)
    with pytest.raises(FreshCaptureReplayError, match="identity mismatch"):
        verify_fresh_capture(tmp_path, replace(expected, **{field: "wrong"}))


@pytest.mark.parametrize("field,value", [
    ("historical_capture", True), ("capture_class", "HISTORICAL"),
    ("receiver_id", "other"),
])
def test_wrong_capture_class_denied(tmp_path, field, value):
    expected, manifest = _fixture(tmp_path)
    manifest[field] = value
    expected = replace(expected, manifest_sha256=_save(tmp_path, manifest))
    with pytest.raises(FreshCaptureReplayError, match="class or receiver"):
        verify_fresh_capture(tmp_path, expected)


def test_manifest_tamper_denied(tmp_path):
    expected, _ = _fixture(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["exit_code"] = 1
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FreshCaptureReplayError, match="manifest hash mismatch"):
        verify_fresh_capture(tmp_path, expected)


def test_rehashed_manifest_without_independent_pin_denied(tmp_path):
    expected, manifest = _fixture(tmp_path)
    manifest["exit_code"] = 1
    _save(tmp_path, manifest)
    with pytest.raises(FreshCaptureReplayError, match="manifest hash mismatch"):
        verify_fresh_capture(tmp_path, expected)


def test_duplicate_manifest_key_denied(tmp_path):
    expected, _ = _fixture(tmp_path)
    path = tmp_path / "manifest.json"
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'), encoding="utf-8")
    with pytest.raises(FreshCaptureReplayError, match="duplicate capture manifest key"):
        verify_fresh_capture(tmp_path, expected)


@pytest.mark.parametrize("filename", ["request.bin", "stdout.jsonl", "stderr.bin"])
def test_raw_byte_tamper_denied(tmp_path, filename):
    expected, _ = _fixture(tmp_path)
    path = tmp_path / filename
    data = path.read_bytes()
    path.write_bytes(b"X" * len(data) if data else b"X")
    with pytest.raises(FreshCaptureReplayError, match="mismatch"):
        verify_fresh_capture(tmp_path, expected)


@pytest.mark.parametrize("field,value", [
    ("stdout_complete", False), ("stderr_complete", False),
    ("cleanup_confirmed", False), ("process_start_count", 2),
    ("provider_call_count", 2), ("timed_out", True), ("exit_code", 1),
])
def test_incomplete_or_over_budget_claim_denied(tmp_path, field, value):
    expected, manifest = _fixture(tmp_path)
    manifest[field] = value
    expected = replace(expected, manifest_sha256=_save(tmp_path, manifest))
    with pytest.raises(FreshCaptureReplayError, match="incomplete capture"):
        verify_fresh_capture(tmp_path, expected)


def test_wrong_response_denied_after_valid_rehash(tmp_path):
    expected, manifest = _fixture(tmp_path)
    stdout = b'{"type":"text","text":"wrong"}\n'
    (tmp_path / "stdout.jsonl").write_bytes(stdout)
    manifest["stdout_sha256"] = hashlib.sha256(stdout).hexdigest()
    manifest["stdout_total_bytes"] = len(stdout)
    expected = replace(expected, manifest_sha256=_save(tmp_path, manifest))
    with pytest.raises(FreshCaptureReplayError, match="response mismatch"):
        verify_fresh_capture(tmp_path, expected)


def test_malformed_stdout_denied_after_valid_rehash(tmp_path):
    expected, manifest = _fixture(tmp_path)
    stdout = b"not jsonl\n"
    (tmp_path / "stdout.jsonl").write_bytes(stdout)
    manifest["stdout_sha256"] = hashlib.sha256(stdout).hexdigest()
    manifest["stdout_total_bytes"] = len(stdout)
    expected = replace(expected, manifest_sha256=_save(tmp_path, manifest))
    with pytest.raises(FreshCaptureReplayError, match="replay failed"):
        verify_fresh_capture(tmp_path, expected)


def test_wrong_task_expectation_denied(tmp_path):
    expected, _ = _fixture(tmp_path)
    with pytest.raises(FreshCaptureReplayError, match="invalid expected task"):
        verify_fresh_capture(tmp_path, replace(expected, task=b"other"))
