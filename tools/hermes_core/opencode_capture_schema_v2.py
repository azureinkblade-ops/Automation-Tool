"""Frozen v2 manifest schema for fresh, capture-only OpenCode evidence.

Non-live. This module only validates and canonicalises data; it can neither
issue authority nor start a process. Schema freeze is not target-artifact
freeze, and a fake-origin manifest is never acceptance evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping

SCHEMA_ID = "hermes.opencode-capture-manifest/v2"
CAPTURE_CLASS = "FRESH_CURRENT_QUALIFICATION"
HISTORICAL_CAPTURE = "NO"
FAKE_ORIGIN = "FAKE_INJECTED_NONLIVE"
FAKE_VERIFICATION = "FAKE_VERIFIER_NONLIVE"
GPU_STATUS_UNRESOLVED = "UNRESOLVED_PREREQUISITE"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED_CLOSED = "FAILED_CLOSED"

# Prerequisites this code can never clear; a live packet must resolve each one
# by separate reviewed evidence and a separate code change.
UNRESOLVED_PREREQUISITES = (
    "AUXILIARY_CALL_BEHAVIOR_UNPROVEN",
    "EGRESS_CONTAINMENT_UNATTESTED",
    "GPU_CPU_ONLY_UNPROVEN",
    "RECEIVER_REQUEST_BYTES_UNPROVEN",
    "TRUSTED_ISSUER_UNBOUND",
)

MANIFEST_FIELDS = (
    "acceptance_eligible", "approval_id", "authorization_id",
    "authorization_sha256", "auxiliary_call_count", "capture_class",
    "capture_status", "child_process_count", "claimed_at",
    "cleanup_confirmed", "config_sha256", "cpu_only_proven", "denied_call_count",
    "ended_at", "execution_origin", "exit_code", "failure_reasons", "files",
    "gpu_policy_status", "historical_capture", "issuer_id",
    "issuer_verification", "manifest_sha256", "model_binding_id", "operator_id",
    "pid", "process_start_count_observed", "provider_budget_id",
    "provider_call_count_forwarded", "provider_calls", "receiver_id", "run_id",
    "schema_id", "source_commit", "started_at", "stderr_bytes",
    "stderr_complete", "stderr_sha256", "stdout_bytes", "stdout_complete",
    "stdout_sha256", "task_sha256", "timed_out", "transport_id",
    "unresolved_prerequisites", "executable_sha256",
)
CALL_FIELDS = (
    "classification", "completed_at", "decision", "forwarded", "received_at",
    "request_bytes", "request_sha256", "response_bytes", "response_sha256",
    "seq",
)
FILE_NAMES = ("request-1.bin", "response-1.bin", "stderr.bin", "stdout.bin")

_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9_:-]{1,128}\Z", re.ASCII)

SCHEMA_FINGERPRINT = hashlib.sha256(json.dumps(
    {"schema": SCHEMA_ID, "fields": sorted(MANIFEST_FIELDS),
     "call_fields": sorted(CALL_FIELDS), "files": sorted(FILE_NAMES)},
    sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


class CaptureSchemaError(ValueError):
    """Manifest does not satisfy the frozen v2 schema."""


def canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def manifest_hash(manifest: Mapping[str, object]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def seal(manifest: Mapping[str, object]) -> dict:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    body["manifest_sha256"] = manifest_hash(body)
    validate_manifest(body)
    return body


def _int(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _hash(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _time(value: object) -> bool:
    return type(value) is str and _TIME.fullmatch(value) is not None


def validate_manifest(manifest: object) -> None:
    """Strict structural validation; raises CaptureSchemaError."""
    if not isinstance(manifest, dict) or set(manifest) != set(MANIFEST_FIELDS):
        raise CaptureSchemaError("manifest keys do not match v2")
    m = manifest
    exact = {
        "schema_id": SCHEMA_ID, "capture_class": CAPTURE_CLASS,
        "historical_capture": HISTORICAL_CAPTURE, "execution_origin": FAKE_ORIGIN,
        "acceptance_eligible": "NO", "issuer_verification": FAKE_VERIFICATION,
        "gpu_policy_status": GPU_STATUS_UNRESOLVED, "cpu_only_proven": "NO",
        "receiver_id": "opencode-cli-agent",
    }
    for key, expected in exact.items():
        if m[key] != expected:
            raise CaptureSchemaError(f"label {key} must be {expected}")
    if m["unresolved_prerequisites"] != list(UNRESOLVED_PREREQUISITES):
        raise CaptureSchemaError("unresolved prerequisites must be recorded")
    if m["capture_status"] not in (STATUS_COMPLETE, STATUS_FAILED_CLOSED):
        raise CaptureSchemaError("invalid capture status")
    reasons = m["failure_reasons"]
    if (type(reasons) is not list or reasons != sorted(set(reasons))
            or any(type(r) is not str or not r for r in reasons)):
        raise CaptureSchemaError("invalid failure reasons")
    if (m["capture_status"] == STATUS_COMPLETE) != (reasons == []):
        raise CaptureSchemaError("status and failure reasons disagree")
    for key in ("issuer_id", "authorization_id", "approval_id", "operator_id",
                "run_id", "provider_budget_id"):
        if type(m[key]) is not str or _ID.fullmatch(m[key]) is None:
            raise CaptureSchemaError(f"invalid {key}")
    if type(m["source_commit"]) is not str or _COMMIT.fullmatch(m["source_commit"]) is None:
        raise CaptureSchemaError("invalid source commit")
    for key in ("authorization_sha256", "executable_sha256", "config_sha256",
                "transport_id", "model_binding_id", "task_sha256",
                "manifest_sha256", "stdout_sha256", "stderr_sha256"):
        if not _hash(m[key]):
            raise CaptureSchemaError(f"invalid hash {key}")
    for key in ("claimed_at", "started_at", "ended_at"):
        if not _time(m[key]):
            raise CaptureSchemaError(f"invalid {key}")
    if not m["claimed_at"] <= m["started_at"] <= m["ended_at"]:
        raise CaptureSchemaError("timestamps out of order")
    for key in ("auxiliary_call_count", "child_process_count", "denied_call_count",
                "process_start_count_observed", "provider_call_count_forwarded",
                "stdout_bytes", "stderr_bytes"):
        if not _int(m[key]):
            raise CaptureSchemaError(f"invalid {key}")
    if not _int(m["pid"], 1) or type(m["exit_code"]) is not int:
        raise CaptureSchemaError("invalid pid or exit code")
    for key in ("cleanup_confirmed", "stderr_complete", "stdout_complete", "timed_out"):
        if type(m[key]) is not bool:
            raise CaptureSchemaError(f"invalid {key}")
    calls = m["provider_calls"]
    if type(calls) is not list or len(calls) > 64:
        raise CaptureSchemaError("invalid provider call journal")
    for index, call in enumerate(calls, 1):
        if not isinstance(call, dict) or set(call) != set(CALL_FIELDS):
            raise CaptureSchemaError("provider call keys do not match v2")
        if call["seq"] != index or type(call["seq"]) is not int:
            raise CaptureSchemaError("provider call sequence")
        if call["decision"] not in ("FORWARDED", "DENIED"):
            raise CaptureSchemaError("provider call decision")
        if type(call["forwarded"]) is not bool or call["forwarded"] != (call["decision"] == "FORWARDED"):
            raise CaptureSchemaError("provider call forwarded flag")
        if type(call["classification"]) is not str or not call["classification"]:
            raise CaptureSchemaError("provider call classification")
        if not _hash(call["request_sha256"]) or not _int(call["request_bytes"]) or not _time(call["received_at"]):
            raise CaptureSchemaError("provider call request fields")
        for key in ("response_sha256", "response_bytes", "completed_at"):
            if call[key] is not None and not (
                (key == "response_sha256" and _hash(call[key]))
                or (key == "response_bytes" and _int(call[key]))
                or (key == "completed_at" and _time(call[key]))):
                raise CaptureSchemaError("provider call response fields")
    forwarded = sum(1 for c in calls if c["forwarded"])
    if m["provider_call_count_forwarded"] != forwarded:
        raise CaptureSchemaError("forwarded count disagrees with journal")
    if m["denied_call_count"] != len(calls) - forwarded:
        raise CaptureSchemaError("denied count disagrees with journal")
    if m["auxiliary_call_count"] > m["denied_call_count"] + forwarded:
        raise CaptureSchemaError("auxiliary count exceeds journal")
    files = m["files"]
    if (not isinstance(files, dict) or set(files) - set(FILE_NAMES)
            or any(not _hash(v) for v in files.values())):
        raise CaptureSchemaError("invalid file hash map")
    if m["capture_status"] == STATUS_COMPLETE:
        if (m["provider_call_count_forwarded"] != 1 or m["denied_call_count"] != 0
                or m["auxiliary_call_count"] != 0 or m["process_start_count_observed"] != 1
                or m["timed_out"] or not m["cleanup_confirmed"] or m["exit_code"] != 0
                or not m["stdout_complete"] or not m["stderr_complete"]
                or set(files) != set(FILE_NAMES)):
            raise CaptureSchemaError("COMPLETE status contradicts accounting")