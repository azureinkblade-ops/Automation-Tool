"""Acceptance-owned, networkless qualification admission; not live authority."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from typing import Callable

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload


class ProviderAdmissionDenied(RuntimeError):
    pass


def utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProviderAdmissionDenied("UTC timestamp required")
    return datetime.fromisoformat(value[:-1] + "+00:00")


@dataclass(frozen=True)
class QualificationScope:
    run_id: str
    source_commit: str
    transport_id: str
    model_binding_id: str
    task_hash: str
    endpoint: str
    model: str
    request_hash: str
    issued_at: str
    expires_at: str

    def payload(self) -> dict:
        for key, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip():
                raise ProviderAdmissionDenied(f"missing scope field: {key}")
        for key, size in (("source_commit", 40), ("transport_id", 64),
                          ("model_binding_id", 64), ("task_hash", 64),
                          ("request_hash", 64)):
            value = getattr(self, key)
            if len(value) != size or any(c not in "0123456789abcdef" for c in value):
                raise ProviderAdmissionDenied(f"invalid identity: {key}")
        if utc(self.issued_at) >= utc(self.expires_at):
            raise ProviderAdmissionDenied("invalid time window")
        return {
            "invocation_authorization_id": "qualification-budget:" + self.run_id,
            "receiver_id": "opencode-cli-agent",
            "binding_id": self.model_binding_id,
            "enablement_id": self.transport_id,
            "execution_request_id": sha256_payload(asdict(self)),
            "attempt_number": 1,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "runtime_scope": "qualification-only",
            "delegation_class": "acceptance-fixture",
            "nonce": self.run_id,
        }


def provision_budget(store: DurableInvocationAuthorizationStore,
                     scope: QualificationScope) -> None:
    """Explicit fixture provisioning, never production invocation issuance."""
    payload = scope.payload()
    store.persist_issued(
        issue_request_id="qualification-budget:" + scope.run_id,
        issue_request_hash=sha256_payload(payload), authorization_payload=payload,
    )


class QualificationProviderGate:
    def __init__(self, store: DurableInvocationAuthorizationStore,
                 scope: QualificationScope, *, forward: Callable[[bytes], bytes]):
        if not callable(forward):
            raise ProviderAdmissionDenied("injected transport required")
        self.store = store
        self.scope = scope
        self.payload = scope.payload()
        self.forward = forward

    def request(self, *, run_id: str, method: str, endpoint: str, model: str,
                body: bytes, now: str, cancelled: bool = False,
                revoked: bool = False) -> bytes:
        def validate():
            if cancelled is not False or revoked is not False:
                raise ProviderAdmissionDenied("cancelled or revoked")
            if (run_id, method, endpoint, model) != (
                self.scope.run_id, "POST", self.scope.endpoint, self.scope.model
            ):
                raise ProviderAdmissionDenied("request outside frozen scope")
            if not isinstance(body, bytes) or len(body) > 65536:
                raise ProviderAdmissionDenied("invalid bounded request")
            if hashlib.sha256(body).hexdigest() != self.scope.request_hash:
                raise ProviderAdmissionDenied("request hash mismatch")
            if not utc(self.scope.issued_at) <= utc(now) < utc(self.scope.expires_at):
                raise ProviderAdmissionDenied("outside time window")

        validate()
        result = self.store.claim(self.payload, consumed_at=now, validate=validate)
        if not result.allowed:
            raise ProviderAdmissionDenied("qualification budget consumed")
        # No retries or refund: a callback failure leaves durable consumption.
        return self.forward(body)
