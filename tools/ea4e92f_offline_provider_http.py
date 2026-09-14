"""Acceptance-only HTTP-shaped request handling; no listener or networking."""

from dataclasses import dataclass
import json

from tools.ea4e92c_provider_call_control import ProviderAdmissionDenied
from tools.hermes_core.durable_invocation_authorization_store import DurableAuthorizationStoreError
from tools.hermes_core.production_accounting import ProductionAccountingError


@dataclass(frozen=True)
class FixtureHttpResponse:
    status: int
    body: bytes


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def reject_constant(value):
    raise ValueError("nonfinite JSON constant")


class OfflineProviderHttpHandler:
    def __init__(self, gate):
        self.gate = gate

    def handle(self, *, method, path, content_type, body, run_id, now,
               cancelled=False, revoked=False):
        if path != "/v1/chat/completions":
            return FixtureHttpResponse(404, b"route denied")
        if method != "POST":
            return FixtureHttpResponse(405, b"method denied")
        if content_type != "application/json":
            return FixtureHttpResponse(415, b"content type denied")
        if not isinstance(body, bytes):
            return FixtureHttpResponse(400, b"byte body required")
        if len(body) > 65536:
            return FixtureHttpResponse(413, b"request too large")
        try:
            request = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object,
                                 parse_constant=reject_constant)
            if not isinstance(request, dict):
                raise ValueError("object required")
            if request.get("model") != self.gate.scope.model:
                raise ValueError("model mismatch")
            if not isinstance(request.get("messages"), list):
                raise ValueError("messages required")
            if request.get("stream", False) is not False:
                raise ValueError("streaming not qualified")
        except (ValueError, UnicodeError, RecursionError):
            return FixtureHttpResponse(400, b"invalid frozen request")
        try:
            response = self.gate.request(
                run_id=run_id, method=method, endpoint=self.gate.scope.endpoint,
                model=request["model"], body=body, now=now,
                cancelled=cancelled, revoked=revoked,
            )
            return FixtureHttpResponse(200, response)
        except ProviderAdmissionDenied:
            return FixtureHttpResponse(403, b"admission denied")
        except (DurableAuthorizationStoreError, ProductionAccountingError):
            return FixtureHttpResponse(503, b"durable state unavailable")
        except Exception:
            return FixtureHttpResponse(502, b"fake upstream failed")
