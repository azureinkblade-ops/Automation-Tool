"""Acceptance-only streaming qualification; injected bytes, never networking."""

from dataclasses import dataclass
import json

from tools.ea4e92c_provider_call_control import ProviderAdmissionDenied
from tools.ea4e92d_fake_provider_accounting import AccountedFakeProviderGate
from tools.hermes_core.durable_invocation_authorization_store import DurableAuthorizationStoreError
from tools.hermes_core.opencode_sse_response import inspect_sse_response
from tools.hermes_core.production_accounting import ProductionAccountingError


@dataclass(frozen=True)
class FakeSseResponse:
    status: int
    content_type: str
    content_encoding: str | None
    chunks: object


@dataclass(frozen=True)
class FakeHttpResponse:
    status: int
    body: bytes


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _deny_constant(_value):
    raise ValueError("nonfinite JSON constant")


class OfflineStreamingQualificationHandler:
    def __init__(self, store, scope, *, respond, ledger, capture_path, clock):
        if not callable(respond):
            raise TypeError("injected fake response required")

        def forward(body):
            response = respond(body)
            if type(response) is not FakeSseResponse:
                raise ValueError("fake SSE response required")
            return inspect_sse_response(
                status=response.status, content_type=response.content_type,
                content_encoding=response.content_encoding, chunks=response.chunks,
            ).raw_bytes

        self.gate = AccountedFakeProviderGate(
            store, scope, forward=forward, ledger=ledger,
            capture_path=capture_path, clock=clock,
        )

    def handle(self, *, method, path, content_type, body, run_id, now,
               cancelled=False, revoked=False):
        if path != "/v1/chat/completions":
            return FakeHttpResponse(404, b"route denied")
        if method != "POST":
            return FakeHttpResponse(405, b"method denied")
        if content_type != "application/json":
            return FakeHttpResponse(415, b"content type denied")
        if type(body) is not bytes:
            return FakeHttpResponse(400, b"byte body required")
        if len(body) > 65536:
            return FakeHttpResponse(413, b"request too large")
        try:
            request = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                                 parse_constant=_deny_constant)
            if (type(request) is not dict
                    or request.get("model") != self.gate.scope.model
                    or type(request.get("messages")) is not list
                    or request.get("stream") is not True):
                raise ValueError("streaming request mismatch")
        except (ValueError, UnicodeError, RecursionError):
            return FakeHttpResponse(400, b"invalid streaming request")
        try:
            raw = self.gate.request(
                run_id=run_id, method=method, endpoint=self.gate.scope.endpoint,
                model=request["model"], body=body, now=now,
                cancelled=cancelled, revoked=revoked,
            )
            return FakeHttpResponse(200, raw)
        except ProviderAdmissionDenied:
            return FakeHttpResponse(403, b"admission denied")
        except (DurableAuthorizationStoreError, ProductionAccountingError):
            return FakeHttpResponse(503, b"durable state unavailable")
        except Exception:
            return FakeHttpResponse(502, b"fake response failed")
