"""Capture-only OpenCode entry point (EA-4E.92GQ). NON-LIVE, default-disabled.

Requires a capture-qualification authorization that an external trusted issuer
already persisted; it never issues authority, never builds a production
activation, and has no process launcher or network client of its own. The
receiver and upstream are injected ports, so only fakes can run in this tree.
Not registered in app.py and not part of any production activation path.

One provider call is enforced at an injected ProviderBoundary the receiver must
route through. That is containment of the cooperative path only: it cannot stop
a receiver that bypasses the boundary (needs OS-level egress containment,
which is an unresolved prerequisite recorded in every manifest).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Callable, Optional, Protocol

from tools.hermes_core import opencode_capture_schema_v2 as schema
from tools.hermes_core.opencode_capture_model_binding import (
    CaptureModelBindingError, parse_binding,
)
from tools.hermes_core.capture_qualification_authority import (
    CaptureArtifactInvalid, CaptureQualificationArtifact,
)
from tools.hermes_core.capture_qualification_store import (
    CaptureQualificationStore, CaptureStoreError,
)

FROZEN_ROUTE = "/v1/chat/completions"
TRIAL_MODEL = "nemotron-3-ultra-free"
TRIAL_TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
MAX_REQUEST_BYTES = 65536
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_STREAM_BYTES = 1024 * 1024


class CaptureEntryDenied(RuntimeError):
    """Refused before any receiver start; no capture directory was created."""


class ProviderCallViolation(RuntimeError):
    """A second, auxiliary or out-of-scope provider call was refused."""


class CaptureFailedClosed(RuntimeError):
    """Receiver ran (credit consumed) but the capture is not acceptable."""

    def __init__(self, result: "CaptureResult") -> None:
        super().__init__("capture failed closed: " + ",".join(result.manifest["failure_reasons"]))
        self.result = result


@dataclass(frozen=True)
class ReceiverResult:
    stdout: bytes
    stderr: bytes
    exit_code: int
    pid: int
    timed_out: bool
    cleanup_confirmed: bool
    stdout_complete: bool
    stderr_complete: bool
    child_process_count: int


class ReceiverPort(Protocol):
    def run(self, task: bytes, boundary: "ProviderBoundary") -> ReceiverResult: ...
    def terminate(self) -> None: ...


@dataclass(frozen=True)
class CaptureResult:
    status: str
    manifest: dict
    directory: Path


_INVALID_RESULT = ReceiverResult(b"", b"", -1, 1, False, False, False, False, 0)


def _valid_result(outcome: object) -> bool:
    if not isinstance(outcome, ReceiverResult):
        return False
    for name, kind in (
        ("stdout", bytes), ("stderr", bytes), ("exit_code", int), ("pid", int),
        ("timed_out", bool), ("cleanup_confirmed", bool),
        ("stdout_complete", bool), ("stderr_complete", bool),
        ("child_process_count", int),
    ):
        if type(getattr(outcome, name)) is not kind:
            return False
    return (len(outcome.stdout) <= MAX_STREAM_BYTES and len(outcome.stderr) <= MAX_STREAM_BYTES
            and outcome.pid >= 1 and outcome.child_process_count >= 0)

def _utc_ok(value: object) -> str:
    if not schema._time(value):
        raise CaptureEntryDenied("clock must return UTC second strings")
    return value


def _write_new(path: Path, data: bytes) -> None:
    """Exclusive create + fsync; never overwrites an existing capture."""
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _task_in_messages(request: dict, task_text: str) -> bool:
    for message in request.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and task_text in content:
            return True
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str) \
                        and task_text in part["text"]:
                    return True
    return False


class ProviderBoundary:
    """Exactly-one-call gate. Every call attempt is journaled; any denial is a
    violation that fails the whole capture, even if the receiver swallows it."""

    def __init__(self, run_dir: Path, *, expected_model: str, task: bytes,
                 upstream: Callable[[bytes], bytes], clock: Callable[[], str],
                 on_violation: Callable[[], None]) -> None:
        self._dir = run_dir
        self._model = expected_model
        self._task_text = task.decode("utf-8", errors="strict")
        self._upstream = upstream
        self._clock = clock
        self._on_violation = on_violation
        self._lock = threading.Lock()
        self._reserved = False
        self.calls: list[dict] = []
        self.violations: list[str] = []
        self.violation_hook_error = False

    def _violate(self, reason: str) -> None:
        if not self.violations:
            try:
                self._on_violation()
            except Exception:
                self.violation_hook_error = True
        self.violations.append(reason)

    def _classify(self, method: str, path: str, body: bytes) -> str:
        if method != "POST" or path != FROZEN_ROUTE:
            return "AUXILIARY_ROUTE"
        if type(body) is not bytes or not body or len(body) > MAX_REQUEST_BYTES:
            return "INVALID_REQUEST"
        try:
            request = json.loads(body.decode("utf-8"), object_pairs_hook=_unique,
                                 parse_constant=lambda _c: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            return "INVALID_REQUEST"
        if (type(request) is not dict or request.get("model") != self._model
                or request.get("stream") is not True
                or type(request.get("messages")) is not list):
            return "INVALID_REQUEST"
        if not _task_in_messages(request, self._task_text):
            return "AUXILIARY_NON_TASK"
        if self._model == TRIAL_MODEL and request != {
            "model": TRIAL_MODEL, "stream": True,
            "messages": [{"role": "user", "content": TRIAL_TASK.decode("ascii")}],
        }:
            return "UNAPPROVED_TRIAL_CONTENT"
        return "TASK_CALL"

    def call(self, *, method: str, path: str, body: bytes) -> bytes:
        with self._lock:
            received = self._clock()
            raw = body if type(body) is bytes else b""
            entry = {
                "seq": len(self.calls) + 1, "classification": "", "decision": "DENIED",
                "forwarded": False, "request_sha256": hashlib.sha256(raw).hexdigest(),
                "request_bytes": len(raw), "response_sha256": None,
                "response_bytes": None, "received_at": received, "completed_at": None,
            }
            self.calls.append(entry)
            classification = self._classify(method, path, body)
            if classification == "TASK_CALL" and self._reserved:
                classification = "SECOND_CALL"
            entry["classification"] = classification
            if classification != "TASK_CALL":
                self._violate(classification)
                entry["completed_at"] = self._clock()
                raise ProviderCallViolation(classification)
            # Reserve before any upstream byte; no refund on any later failure.
            self._reserved = True
            try:
                _write_new(self._dir / "call-reserved.marker", b"1")
                _write_new(self._dir / "request-1.bin", body)
            except OSError:
                entry["classification"] = "CAPTURE_WRITE_FAILED"
                self._violate("CAPTURE_WRITE_FAILED")
                entry["completed_at"] = self._clock()
                raise ProviderCallViolation("CAPTURE_WRITE_FAILED")
            entry["decision"], entry["forwarded"] = "FORWARDED", True
            try:
                response = self._upstream(body)
                if type(response) is not bytes or len(response) > MAX_RESPONSE_BYTES:
                    raise ValueError("invalid bounded response")
                _write_new(self._dir / "response-1.bin", response)
            except Exception:
                entry["completed_at"] = self._clock()
                self._violate("UPSTREAM_OR_RESPONSE_CAPTURE_FAILED")
                raise ProviderCallViolation("UPSTREAM_OR_RESPONSE_CAPTURE_FAILED")
            entry["response_sha256"] = hashlib.sha256(response).hexdigest()
            entry["response_bytes"] = len(response)
            entry["completed_at"] = self._clock()
            return response


class OpenCodeCaptureEntry:
    """Default-disabled. `enabled` must be the boolean True."""

    def __init__(self, *, store: CaptureQualificationStore, capture_root: Path,
                  trusted_issuer_id: str, clock: Callable[[], str],
                  issuer_verifier: Optional[Callable[[CaptureQualificationArtifact, str], str]] = None,
                  binding_verifier: Optional[Callable[[str, str], str]] = None,
                  enabled: bool = False) -> None:
        self._store = store
        self._root = Path(capture_root)
        self._issuer = trusted_issuer_id
        self._clock = clock
        self._verifier = issuer_verifier
        self._binding_verifier = binding_verifier
        self._enabled = enabled

    def run(self, *, artifact: CaptureQualificationArtifact, issue_request_hash: str,
            task: bytes, binding_bytes: bytes, expected_request_model: str,
            receiver: ReceiverPort,
            upstream: Callable[[bytes], bytes], source_commit: str,
            executable_sha256: str, config_sha256: str, transport_id: str,
            model_binding_id: str, provider_budget_id: str,
            receiver_id: str = "opencode-cli-agent") -> CaptureResult:
        # ---- admission: every denial happens before a start and consumes nothing
        if self._enabled is not True:
            raise CaptureEntryDenied("capture entry disabled")
        if not callable(self._verifier) or type(self._issuer) is not str or not self._issuer:
            raise CaptureEntryDenied("trusted capture issuer unbound")
        if not isinstance(artifact, CaptureQualificationArtifact):
            raise CaptureEntryDenied("capture authorization required")
        if not callable(upstream) or not callable(getattr(receiver, "run", None)) \
                or not callable(getattr(receiver, "terminate", None)):
            raise CaptureEntryDenied("injected receiver and upstream required")
        if type(expected_request_model) is not str or not expected_request_model:
            raise CaptureEntryDenied("bound request model required")
        if not callable(self._binding_verifier):
            raise CaptureEntryDenied("trusted model binding verifier unbound")
        try:
            verified = self._verifier(artifact, issue_request_hash)
        except Exception as exc:
            raise CaptureEntryDenied("issuer verification failed") from exc
        if verified != self._issuer:
            raise CaptureEntryDenied("issuer identity mismatch")
        try:
            binding = parse_binding(binding_bytes)
        except CaptureModelBindingError as exc:
            raise CaptureEntryDenied("canonical model binding required") from exc
        if (binding.binding_id != artifact.model_binding_id
                or binding.request_model_id != expected_request_model
                or binding.runtime_sha256 != artifact.executable_sha256
                or binding.config_sha256 != artifact.config_sha256
                or binding.transport_id != artifact.transport_id):
            raise CaptureEntryDenied("model binding differs from authorization")
        try:
            bound_model = self._binding_verifier(
                artifact.model_binding_id, expected_request_model)
        except Exception as exc:
            raise CaptureEntryDenied("model binding verification failed") from exc
        if type(bound_model) is not str or bound_model != expected_request_model:
            raise CaptureEntryDenied("request model differs from authorized binding")
        try:
            task.decode("utf-8")
        except (AttributeError, UnicodeError) as exc:
            raise CaptureEntryDenied("task must be UTF-8 bytes") from exc
        if binding.model_id == TRIAL_MODEL and task != TRIAL_TASK:
            raise CaptureEntryDenied("trial model requires the frozen synthetic task")
        run_dir = self._root / ("run-" + hashlib.sha256(artifact.run_id.encode("ascii")).hexdigest()[:32])
        if not self._root.is_dir() or self._root.is_symlink() or run_dir.exists():
            raise CaptureEntryDenied("capture root unavailable or run already exists")
        try:
            state = self._store.inspect(artifact.authorization_id)
            if (state.artifact != artifact or state.consumed
                    or state.cancelled_at is not None or state.revoked_at is not None):
                raise CaptureEntryDenied("authorization not in ISSUED state")
            claimed_at = _utc_ok(self._clock())
            if not self._store.claim(
                artifact, task=task, now=claimed_at, receiver_id=receiver_id,
                source_commit=source_commit, executable_sha256=executable_sha256,
                config_sha256=config_sha256, transport_id=transport_id,
                model_binding_id=model_binding_id, provider_budget_id=provider_budget_id,
            ):
                raise CaptureEntryDenied("authorization already consumed")
        except (CaptureArtifactInvalid, CaptureStoreError) as exc:
            raise CaptureEntryDenied("authorization check failed: " + type(exc).__name__) from exc

        # ---- credit is now durably consumed; nothing below can refund it
        run_dir.mkdir()
        _write_new(run_dir / "authorization.json", artifact.canonical_bytes())
        _write_new(run_dir / "model-binding.json", binding.canonical_bytes)
        terminated = []

        def terminate_once() -> None:
            if not terminated:
                terminated.append(True)
                receiver.terminate()

        boundary = ProviderBoundary(
            run_dir, expected_model=expected_request_model, task=task,
            upstream=upstream, clock=self._clock, on_violation=terminate_once,
        )
        reasons: set[str] = set()
        started_at = _utc_ok(self._clock())
        start_count = 1  # observed here: this is the only receiver.run call site
        outcome: Optional[ReceiverResult] = None
        try:
            outcome = receiver.run(task, boundary)
        except Exception as exc:
            reasons.add("RECEIVER_EXCEPTION:" + type(exc).__name__)
            try:
                terminate_once()
            except Exception:
                reasons.add("TERMINATE_FAILED")
        ended_at = _utc_ok(self._clock())

        if not _valid_result(outcome):
            reasons.add("INVALID_RECEIVER_RESULT")
            outcome = _INVALID_RESULT
        reasons.update(boundary.violations)
        if boundary.violation_hook_error:
            reasons.add("TERMINATE_FAILED")
        forwarded = sum(1 for c in boundary.calls if c["forwarded"])
        denied = len(boundary.calls) - forwarded
        if forwarded != 1:
            reasons.add("PROVIDER_CALL_COUNT_NOT_ONE")
        if outcome.exit_code != 0:
            reasons.add("NONZERO_EXIT")
        if outcome.timed_out:
            reasons.add("TIMED_OUT")
        if not outcome.cleanup_confirmed:
            reasons.add("CLEANUP_NOT_CONFIRMED")
        if not outcome.stdout_complete or not outcome.stderr_complete:
            reasons.add("STREAM_INCOMPLETE")
        if not outcome.stdout:
            reasons.add("EMPTY_STDOUT")
        if outcome.child_process_count != 0:
            reasons.add("CHILD_PROCESSES_OBSERVED")

        _write_new(run_dir / "stdout.bin", outcome.stdout)
        _write_new(run_dir / "stderr.bin", outcome.stderr)
        files = {}
        for name in schema.FILE_NAMES:
            path = run_dir / name
            if path.is_file():
                files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        failure = sorted(reasons)
        manifest = schema.seal({
            "schema_id": schema.SCHEMA_ID, "capture_class": schema.CAPTURE_CLASS,
            "historical_capture": schema.HISTORICAL_CAPTURE,
            "execution_origin": schema.FAKE_ORIGIN, "acceptance_eligible": "NO",
            "capture_status": schema.STATUS_FAILED_CLOSED if failure else schema.STATUS_COMPLETE,
            "failure_reasons": failure,
            "issuer_id": self._issuer, "issuer_verification": schema.FAKE_VERIFICATION,
            "authorization_id": artifact.authorization_id,
            "approval_id": artifact.approval_id, "operator_id": artifact.operator_id,
            "authorization_sha256": artifact.sha256(), "run_id": artifact.run_id,
            "receiver_id": artifact.receiver_id, "source_commit": artifact.source_commit,
            "executable_sha256": artifact.executable_sha256,
            "config_sha256": artifact.config_sha256, "transport_id": artifact.transport_id,
            "model_binding_id": artifact.model_binding_id,
            "provider_budget_id": artifact.provider_budget_id,
            "task_sha256": artifact.task_sha256,
            "gpu_policy_status": schema.GPU_STATUS_UNRESOLVED, "cpu_only_proven": "NO",
            "unresolved_prerequisites": list(schema.UNRESOLVED_PREREQUISITES),
            "claimed_at": claimed_at, "started_at": started_at, "ended_at": ended_at,
            "pid": outcome.pid, "exit_code": outcome.exit_code,
            "timed_out": outcome.timed_out, "cleanup_confirmed": outcome.cleanup_confirmed,
            "child_process_count": outcome.child_process_count,
            "process_start_count_observed": start_count,
            "stdout_sha256": hashlib.sha256(outcome.stdout).hexdigest(),
            "stdout_bytes": len(outcome.stdout), "stdout_complete": outcome.stdout_complete,
            "stderr_sha256": hashlib.sha256(outcome.stderr).hexdigest(),
            "stderr_bytes": len(outcome.stderr), "stderr_complete": outcome.stderr_complete,
            "provider_call_count_forwarded": forwarded, "denied_call_count": denied,
            "auxiliary_call_count": denied, "provider_calls": boundary.calls,
            "files": files,
        })
        _write_new(run_dir / "manifest.json", schema.canonical_bytes(manifest))
        result = CaptureResult(manifest["capture_status"], manifest, run_dir)
        if failure:
            raise CaptureFailedClosed(result)
        return result


def verify_capture_v2(directory: Path) -> dict:
    """Offline integrity check of a retained v2 capture; returns the manifest.

    Verifies schema, manifest hash, file hashes and journal consistency. It does
    NOT make a fake-origin capture acceptance evidence and does not replay."""
    directory = Path(directory)
    raw = (directory / "manifest.json").read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError) as exc:
        raise schema.CaptureSchemaError("invalid manifest JSON") from exc
    schema.validate_manifest(manifest)
    if raw != schema.canonical_bytes(manifest) or manifest["manifest_sha256"] != schema.manifest_hash(manifest):
        raise schema.CaptureSchemaError("manifest not canonical or hash mismatch")
    for name, digest in manifest["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise schema.CaptureSchemaError("file hash mismatch: " + name)
    for stream in ("stdout", "stderr"):
        data = (directory / f"{stream}.bin").read_bytes()
        if (hashlib.sha256(data).hexdigest() != manifest[f"{stream}_sha256"]
                or len(data) != manifest[f"{stream}_bytes"]):
            raise schema.CaptureSchemaError(stream + " mismatch")
    for call in manifest["provider_calls"]:
        if call["forwarded"]:
            if hashlib.sha256((directory / "request-1.bin").read_bytes()).hexdigest() != call["request_sha256"]:
                raise schema.CaptureSchemaError("request bytes mismatch")
            if call["response_sha256"] is not None and hashlib.sha256(
                    (directory / "response-1.bin").read_bytes()).hexdigest() != call["response_sha256"]:
                raise schema.CaptureSchemaError("response bytes mismatch")
    return manifest


def verify_bound_capture_v2(directory: Path) -> dict:
    """Require the supplementary canonical binding for a new fake v2 capture.

    The frozen v2 manifest remains unchanged; older fake captures continue to
    use verify_capture_v2. This is not live or acceptance qualification.
    """
    directory = Path(directory)
    manifest = verify_capture_v2(directory)
    try:
        binding = parse_binding((directory / "model-binding.json").read_bytes())
    except (OSError, CaptureModelBindingError) as exc:
        raise schema.CaptureSchemaError("bound model material missing or invalid") from exc
    if (binding.binding_id != manifest["model_binding_id"]
            or binding.runtime_sha256 != manifest["executable_sha256"]
            or binding.config_sha256 != manifest["config_sha256"]
            or binding.transport_id != manifest["transport_id"]):
        raise schema.CaptureSchemaError("binding differs from manifest")
    for call in manifest["provider_calls"]:
        if call["forwarded"]:
            try:
                request = json.loads((directory / "request-1.bin").read_bytes().decode("utf-8"),
                                     object_pairs_hook=_unique)
            except (OSError, ValueError, UnicodeError) as exc:
                raise schema.CaptureSchemaError("bound request invalid") from exc
            if type(request) is not dict or request.get("model") != binding.request_model_id:
                raise schema.CaptureSchemaError("request model differs from binding")
    return manifest
