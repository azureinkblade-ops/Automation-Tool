"""Networkless, injected-response qualification for a dynamic inert Kilo body."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import hmac

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_inert_request_shape import (
    InertRequestDenied,
    inspect_inert_kilo_request,
)
from tools.hermes_core.opencode_sse_response import inspect_sse_response


class DynamicFakeDenied(ValueError):
    pass


def _utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DynamicFakeDenied("UTC timestamp required")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DynamicFakeDenied("invalid UTC timestamp") from exc


@dataclass(frozen=True)
class DynamicFakeScope:
    run_id: str
    source_commit: str
    transport_id: str
    model_binding_id: str
    task_hash: str
    network_id: str
    container_id: str
    token_sha256: str
    issued_at: str
    expires_at: str

    def payload(self):
        if not self.run_id:
            raise DynamicFakeDenied("run identity missing")
        for field, length in (("source_commit", 40), ("transport_id", 64),
                              ("model_binding_id", 64), ("task_hash", 64),
                              ("network_id", 64), ("container_id", 64),
                              ("token_sha256", 64)):
            value = getattr(self, field)
            if not isinstance(value, str) or len(value) != length or any(
                    c not in "0123456789abcdef" for c in value):
                raise DynamicFakeDenied(f"invalid scope identity: {field}")
        if _utc(self.issued_at) >= _utc(self.expires_at):
            raise DynamicFakeDenied("invalid time window")
        return {
            "invocation_authorization_id": "kilo-dynamic-fake:" + self.run_id,
            "receiver_id": "kilo-linux-inert-fake",
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


def provision_dynamic_fake_budget(store: DurableInvocationAuthorizationStore,
                                  scope: DynamicFakeScope):
    """Issue only a test fixture budget; never production authority."""
    payload = scope.payload()
    store.persist_issued(issue_request_id=payload["invocation_authorization_id"],
                         issue_request_hash=sha256_payload(payload),
                         authorization_payload=payload)


@dataclass(frozen=True)
class DynamicFakeResult:
    response_bytes: bytes
    body_sha256: str
    body_bytes: int


class KiloDynamicFakeGateway:
    def __init__(self, store: DurableInvocationAuthorizationStore,
                 scope: DynamicFakeScope, *, verify_peer, respond):
        if not callable(verify_peer) or not callable(respond):
            raise DynamicFakeDenied("injected fake peer and response required")
        self.store = store
        self.scope = scope
        self.payload = scope.payload()
        self.verify_peer = verify_peer
        self.respond = respond

    def request(self, *, run_id, task_hash, connection_context, method, path,
                content_type, authorization, body, now, cancelled=False,
                revoked=False):
        def validate():
            if cancelled is not False or revoked is not False:
                raise DynamicFakeDenied("cancelled or revoked")
            if (run_id, task_hash, method, path, content_type) != (
                    self.scope.run_id, self.scope.task_hash, "POST",
                    "/v1/chat/completions", "application/json"):
                raise DynamicFakeDenied("request route or scope denied")
            if not isinstance(authorization, str) or not hmac.compare_digest(
                    hashlib.sha256(authorization.encode("utf-8")).hexdigest(),
                    self.scope.token_sha256):
                raise DynamicFakeDenied("child token denied")
            if self.verify_peer(self.scope, connection_context) is not True:
                raise DynamicFakeDenied("peer binding denied")
            try:
                observation = inspect_inert_kilo_request(body)
            except InertRequestDenied as exc:
                raise DynamicFakeDenied("inert body shape denied") from exc
            if not _utc(self.scope.issued_at) <= _utc(now) < _utc(self.scope.expires_at):
                raise DynamicFakeDenied("time window denied")
            return observation

        observation = validate()

        def validate_claim():
            validate()
            return None

        claim = self.store.claim(self.payload, consumed_at=now,
                                 validate=validate_claim)
        if not claim.allowed:
            raise DynamicFakeDenied("one-request budget consumed or unavailable")
        # Only the injected fake callback runs after the durable claim.
        response = self.respond(body)
        raw = inspect_sse_response(status=response.status,
                                   content_type=response.content_type,
                                   content_encoding=response.content_encoding,
                                   chunks=response.chunks).raw_bytes
        return DynamicFakeResult(raw, observation["body_sha256"],
                                 observation["body_bytes"])
