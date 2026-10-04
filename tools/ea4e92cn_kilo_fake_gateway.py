"""Networkless Kilo gateway qualification. No listener or upstream transport."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import hmac
import json

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.opencode_sse_response import inspect_sse_response


class FakeGatewayDenied(ValueError):
    pass


def _utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FakeGatewayDenied("UTC timestamp required")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FakeGatewayDenied("duplicate JSON key")
        result[key] = value
    return result


def _deny_constant(_value):
    raise FakeGatewayDenied("nonfinite JSON constant")


@dataclass(frozen=True)
class KiloFakeScope:
    run_id: str
    source_commit: str
    transport_id: str
    model_binding_id: str
    task_hash: str
    request_hash: str
    token_sha256: str
    model: str
    issued_at: str
    expires_at: str

    def payload(self):
        if not self.run_id or not self.model:
            raise FakeGatewayDenied("scope identity missing")
        for key, length in (("source_commit", 40), ("transport_id", 64),
                            ("model_binding_id", 64), ("task_hash", 64),
                            ("request_hash", 64), ("token_sha256", 64)):
            value = getattr(self, key)
            if len(value) != length or any(c not in "0123456789abcdef" for c in value):
                raise FakeGatewayDenied(f"invalid scope identity: {key}")
        if _utc(self.issued_at) >= _utc(self.expires_at):
            raise FakeGatewayDenied("invalid time window")
        return {
            "invocation_authorization_id": "kilo-fake-budget:" + self.run_id,
            "receiver_id": "kilo-cli-agent",
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


def provision_fake_budget(store: DurableInvocationAuthorizationStore, scope: KiloFakeScope):
    """Explicit test fixture issuance; never production authority."""
    payload = scope.payload()
    store.persist_issued(issue_request_id=payload["invocation_authorization_id"],
                         issue_request_hash=sha256_payload(payload),
                         authorization_payload=payload)


class KiloFakeGateway:
    def __init__(self, store: DurableInvocationAuthorizationStore,
                 scope: KiloFakeScope, *, respond):
        if not callable(respond):
            raise FakeGatewayDenied("injected fake response required")
        self.store = store
        self.scope = scope
        self.payload = scope.payload()
        self.respond = respond

    def request(self, *, run_id, method, path, content_type, authorization,
                body, now, cancelled=False, revoked=False):
        def validate():
            if cancelled is not False or revoked is not False:
                raise FakeGatewayDenied("cancelled or revoked")
            if (run_id, method, path, content_type) != (
                    self.scope.run_id, "POST", "/v1/chat/completions", "application/json"):
                raise FakeGatewayDenied("request route or scope denied")
            if not isinstance(authorization, str) or not hmac.compare_digest(
                    hashlib.sha256(authorization.encode("utf-8")).hexdigest(),
                    self.scope.token_sha256):
                raise FakeGatewayDenied("local token denied")
            if type(body) is not bytes or len(body) > 65536:
                raise FakeGatewayDenied("request bytes denied")
            if hashlib.sha256(body).hexdigest() != self.scope.request_hash:
                raise FakeGatewayDenied("request hash denied")
            try:
                request = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                                     parse_constant=_deny_constant)
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise FakeGatewayDenied("request JSON denied") from exc
            if (type(request) is not dict or request.get("model") != self.scope.model
                    or type(request.get("messages")) is not list
                    or request.get("stream") is not True):
                raise FakeGatewayDenied("streaming request denied")
            if not _utc(self.scope.issued_at) <= _utc(now) < _utc(self.scope.expires_at):
                raise FakeGatewayDenied("time window denied")
            return None

        validate()
        claim = self.store.claim(self.payload, consumed_at=now, validate=validate)
        if not claim.allowed:
            raise FakeGatewayDenied("one-request budget consumed or unavailable")
        # The injected callback has no network capability. Failure never refunds the claim.
        response = self.respond(body)
        return inspect_sse_response(status=response.status,
                                    content_type=response.content_type,
                                    content_encoding=response.content_encoding,
                                    chunks=response.chunks).raw_bytes
