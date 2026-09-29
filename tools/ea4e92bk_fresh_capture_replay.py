"""Read-only, offline verification of a prospective OpenCode capture fixture."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.opencode_adapter import OpenCodeParseError, OpenCodeReceiverAdapter


class FreshCaptureReplayError(ValueError):
    pass


_TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
_RESPONSE = "EA4E92_OPENCODE_CURRENT_REPLAY_OK"


@dataclass(frozen=True)
class FreshCaptureExpectation:
    run_id: str
    attempt_id: str
    authorization_id: str
    source_commit: str
    executable_sha256: str
    config_sha256: str
    transport_id: str
    model_binding_id: str
    task: bytes
    expected_text: str
    manifest_sha256: str


_IDENTITY_FIELDS = (
    "run_id", "attempt_id", "authorization_id", "source_commit",
    "executable_sha256", "config_sha256", "transport_id", "model_binding_id",
)
_REQUIRED_FIELDS = set(_IDENTITY_FIELDS) | {
    "schema_version", "capture_class", "historical_capture", "receiver_id",
    "task_sha256", "stdout_sha256", "stderr_sha256", "stdout_total_bytes",
    "stderr_total_bytes", "started_at_utc", "ended_at_utc", "pid",
    "exit_code", "timed_out", "cancelled", "stdout_complete",
    "stderr_complete", "cleanup_confirmed", "process_start_count",
    "provider_call_count", "manifest_sha256",
}


def _read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise FreshCaptureReplayError("capture file is a symlink")
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError as exc:
        raise FreshCaptureReplayError("capture file unavailable") from exc
    if len(data) > limit:
        raise FreshCaptureReplayError("capture file exceeds retention limit")
    return data


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise FreshCaptureReplayError("invalid capture timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreshCaptureReplayError("invalid capture timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise FreshCaptureReplayError("capture timestamp is not UTC")
    return parsed.astimezone(timezone.utc)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise FreshCaptureReplayError("duplicate capture manifest key")
        result[key] = value
    return result


def verify_fresh_capture(directory: Path, expected: FreshCaptureExpectation) -> str:
    """Verify retained bytes and replay them with the committed production parser.

    Provider/process counts are manifest claims, not independent observations.
    """
    if expected.task != _TASK or expected.expected_text != _RESPONSE:
        raise FreshCaptureReplayError("invalid expected task")
    if any(not getattr(expected, field) for field in _IDENTITY_FIELDS) or not expected.expected_text:
        raise FreshCaptureReplayError("missing expected identity")
    try:
        manifest = json.loads(
            _read_bounded(directory / "manifest.json", 65536),
            object_pairs_hook=_unique_object,
        )
    except FreshCaptureReplayError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise FreshCaptureReplayError("invalid capture manifest") from exc
    if not isinstance(manifest, dict) or set(manifest) != _REQUIRED_FIELDS:
        raise FreshCaptureReplayError("unexpected capture manifest fields")
    digest = manifest.pop("manifest_sha256")
    if (not isinstance(digest, str) or digest != expected.manifest_sha256
            or digest != sha256_payload(manifest)):
        raise FreshCaptureReplayError("capture manifest hash mismatch")
    if (manifest["schema_version"] != 1
            or manifest["capture_class"] != "FRESH_CURRENT_QUALIFICATION"
            or manifest["historical_capture"] is not False
            or manifest["receiver_id"] != "opencode-cli-agent"):
        raise FreshCaptureReplayError("wrong capture class or receiver")
    if any(manifest[field] != getattr(expected, field) for field in _IDENTITY_FIELDS):
        raise FreshCaptureReplayError("capture identity mismatch")
    if (manifest["task_sha256"] != hashlib.sha256(expected.task).hexdigest()
            or _read_bounded(directory / "request.bin", 65536) != expected.task):
        raise FreshCaptureReplayError("capture task mismatch")
    if not _utc(manifest["started_at_utc"]) <= _utc(manifest["ended_at_utc"]):
        raise FreshCaptureReplayError("capture timestamps reversed")
    if (type(manifest["pid"]) is not int or manifest["pid"] <= 0
            or type(manifest["exit_code"]) is not int or manifest["exit_code"] != 0
            or manifest["timed_out"] is not False or manifest["cancelled"] is not False
            or manifest["stdout_complete"] is not True
            or manifest["stderr_complete"] is not True
            or manifest["cleanup_confirmed"] is not True
            or type(manifest["process_start_count"]) is not int
            or manifest["process_start_count"] != 1
            or type(manifest["provider_call_count"]) is not int
            or manifest["provider_call_count"] != 1):
        raise FreshCaptureReplayError("incomplete capture or accounting claim")
    stdout = _read_bounded(directory / "stdout.jsonl", 1024 * 1024)
    stderr = _read_bounded(directory / "stderr.bin", 128 * 1024)
    for name, data in (("stdout", stdout), ("stderr", stderr)):
        if (type(manifest[f"{name}_total_bytes"]) is not int
                or manifest[f"{name}_total_bytes"] != len(data)
                or manifest[f"{name}_sha256"] != hashlib.sha256(data).hexdigest()):
            raise FreshCaptureReplayError(f"{name} capture bytes mismatch")
    if not stdout:
        raise FreshCaptureReplayError("empty stdout capture")
    try:
        parsed = OpenCodeReceiverAdapter().parse_output(stdout.decode("utf-8"))
    except (UnicodeError, OpenCodeParseError) as exc:
        raise FreshCaptureReplayError("capture replay failed") from exc
    if parsed["type"] != "text" or parsed["text"] != expected.expected_text:
        raise FreshCaptureReplayError("capture response mismatch")
    return parsed["text"]
