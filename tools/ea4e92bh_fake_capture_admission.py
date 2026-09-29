"""Acceptance-only receiver-start admission; no runtime or process launcher."""

from dataclasses import asdict, dataclass
from datetime import timedelta
import hashlib
from typing import Callable

from tools.ea4e92c_provider_call_control import utc
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload


class CaptureAdmissionDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class CaptureOnlyScope:
    run_id: str
    receiver_id: str
    source_commit: str
    executable_sha256: str
    config_sha256: str
    transport_id: str
    model_binding_id: str
    task_hash: str
    provider_budget_id: str
    issued_at: str
    expires_at: str

    def payload(self) -> dict:
        if not self.run_id or self.provider_budget_id != "qualification-budget:" + self.run_id:
            raise CaptureAdmissionDenied("missing run or provider budget")
        if self.receiver_id != "opencode-cli-agent":
            raise CaptureAdmissionDenied("receiver outside capture scope")
        for key, length in (("source_commit", 40), ("executable_sha256", 64),
                            ("config_sha256", 64), ("transport_id", 64),
                            ("model_binding_id", 64), ("task_hash", 64)):
            value = getattr(self, key)
            if len(value) != length or any(c not in "0123456789abcdef" for c in value):
                raise CaptureAdmissionDenied(f"invalid {key}")
        if not utc(self.issued_at) < utc(self.expires_at) <= utc(self.issued_at) + timedelta(minutes=5):
            raise CaptureAdmissionDenied("invalid capture window")
        return {
            "invocation_authorization_id": "capture-budget:" + self.run_id,
            "receiver_id": self.receiver_id,
            "binding_id": self.model_binding_id,
            "enablement_id": self.transport_id,
            "execution_request_id": sha256_payload(asdict(self)),
            "attempt_number": 1,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "runtime_scope": "capture-qualification-only",
            "delegation_class": "acceptance-fixture",
            "nonce": self.run_id,
        }


def provision_fake_capture_budget(
    store: DurableInvocationAuthorizationStore, scope: CaptureOnlyScope,
) -> None:
    """Provision isolated fixture state, never production invocation authority."""
    payload = scope.payload()
    store.persist_issued(
        issue_request_id="capture-budget:" + scope.run_id,
        issue_request_hash=sha256_payload(payload),
        authorization_payload=payload,
    )


@dataclass(frozen=True)
class FakeCaptureEvidence:
    stdout: bytes
    stderr: bytes
    stdout_complete: bool
    stderr_complete: bool
    cleanup_confirmed: bool
    process_start_count: int
    provider_call_count: int


class FakeCaptureAdmission:
    def __init__(
        self, store: DurableInvocationAuthorizationStore, scope: CaptureOnlyScope,
        *, capture: Callable[[bytes], FakeCaptureEvidence],
    ) -> None:
        if not callable(capture):
            raise CaptureAdmissionDenied("injected fake capture required")
        self.store = store
        self.scope = scope
        self.payload = scope.payload()
        self.capture = capture

    def attempt(
        self, *, run_id: str, receiver_id: str, source_commit: str,
        executable_sha256: str, config_sha256: str, transport_id: str,
        model_binding_id: str, provider_budget_id: str, task: bytes,
        now: str, cancelled: bool = False, revoked: bool = False,
    ) -> FakeCaptureEvidence:
        def validate() -> None:
            if cancelled is not False or revoked is not False:
                raise CaptureAdmissionDenied("cancelled or revoked")
            if (run_id, receiver_id, source_commit, executable_sha256,
                    config_sha256, transport_id, model_binding_id,
                    provider_budget_id) != (
                    self.scope.run_id, self.scope.receiver_id,
                    self.scope.source_commit, self.scope.executable_sha256,
                    self.scope.config_sha256, self.scope.transport_id,
                    self.scope.model_binding_id, self.scope.provider_budget_id,
            ):
                raise CaptureAdmissionDenied("capture identity mismatch")
            if not isinstance(task, bytes) or not task or len(task) > 65536:
                raise CaptureAdmissionDenied("invalid bounded task")
            if hashlib.sha256(task).hexdigest() != self.scope.task_hash:
                raise CaptureAdmissionDenied("task hash mismatch")
            if not utc(self.scope.issued_at) <= utc(now) < utc(self.scope.expires_at):
                raise CaptureAdmissionDenied("outside capture window")

        validate()
        claim = self.store.claim(self.payload, consumed_at=now, validate=validate)
        if not claim.allowed:
            raise CaptureAdmissionDenied("capture budget consumed")
        evidence = self.capture(task)
        if (
            not isinstance(evidence, FakeCaptureEvidence)
            or not isinstance(evidence.stdout, bytes)
            or not evidence.stdout
            or not isinstance(evidence.stderr, bytes)
            or not evidence.stdout_complete or not evidence.stderr_complete
            or not evidence.cleanup_confirmed
            or type(evidence.process_start_count) is not int
            or evidence.process_start_count != 1
            or type(evidence.provider_call_count) is not int
            or evidence.provider_call_count != 1
        ):
            raise CaptureAdmissionDenied("incomplete or over-budget fake capture")
        return evidence
