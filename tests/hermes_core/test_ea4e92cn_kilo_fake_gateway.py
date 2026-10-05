"""Kilo gateway contract tests with injected bytes only; never starts a receiver."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json

import pytest

from tools.ea4e92cn_kilo_fake_gateway import (
    FakeGatewayDenied, KiloFakeGateway, KiloFakeScope, provision_fake_budget,
)
from tools.ea4e92bw_fake_streaming_qualification import FakeSseResponse
from tools.ea4e92cp_kilo_request_shape import summarize_request_shape
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreConflict, DurableAuthorizationStoreError,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.opencode_sse_response import SseResponseDenied


BODY = b'{"model":"ea4e-inert","messages":[],"stream":true}'
TOKEN = "Bearer dummy-local-token"
NOW = "2026-10-04T00:00:01Z"
SSE = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'


def fixture(root, respond=None, *, body=BODY):
    scope = KiloFakeScope(
        run_id="kilo-fake-run", source_commit="a" * 40,
        transport_id="b" * 64, model_binding_id="c" * 64,
        task_hash="d" * 64, request_hash=hashlib.sha256(body).hexdigest(),
        token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
        model="ea4e-inert", issued_at="2026-10-04T00:00:00Z",
        expires_at="2026-10-04T00:05:00Z",
    )
    store = DurableInvocationAuthorizationStore.initialize(
        root / "budget.sqlite3", anchor_path=root / "anchor.json")
    provision_fake_budget(store, scope)
    if respond is None:
        respond = lambda body: FakeSseResponse(200, "text/event-stream", None,
                                                ((SSE, 0),))
    return KiloFakeGateway(store, scope, respond=respond)


def request(gate, **changes):
    values = dict(run_id=gate.scope.run_id, method="POST",
                  path="/v1/chat/completions", content_type="application/json",
                  authorization=TOKEN, body=BODY, now=NOW)
    values.update(changes)
    return gate.request(**values)


def test_one_streaming_request_then_restart_replay_denied(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or
                   FakeSseResponse(200, "text/event-stream", None, ((SSE, 0),)))
    assert gate.payload["receiver_id"] == "kilo-cli-agent"
    assert request(gate) == SSE
    reopened = DurableInvocationAuthorizationStore(
        gate.store.path, anchor_path=gate.store.anchor_path)
    retry = KiloFakeGateway(reopened, gate.scope, respond=gate.respond)
    with pytest.raises(FakeGatewayDenied):
        request(retry)
    assert reopened.consumed_count() == 1
    assert calls == [BODY]


def test_concurrent_requests_reach_callback_once(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or
                   FakeSseResponse(200, "text/event-stream", None, ((SSE, 0),)))

    def attempt(_):
        try:
            return request(gate)
        except FakeGatewayDenied:
            return b"denied"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(SSE) == 1
    assert results.count(b"denied") == 3
    assert calls == [BODY]


@pytest.mark.parametrize("size, allowed", [
    (64878, True), (65536, True), (65537, False),
])
def test_synthetic_observed_shape_and_size_boundary(tmp_path, size, allowed):
    payload = {
        "model": "ea4e-inert", "stream": True, "stream_options": {},
        "tools": [], "tool_choice": "auto", "max_tokens": 64,
        "messages": [
            {"role": "system", "content": ""},
            {"role": "user", "content": ["synthetic only"]},
        ],
    }

    def encode():
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    payload["messages"][0]["content"] = "x" * (64878 - len(encode()))
    body = encode() + b" " * (size - 64878)
    assert len(body) == size
    if size == 64878:
        shape = summarize_request_shape(body, expected_model="ea4e-inert")
        assert shape["message_count"] == 2
        assert shape["role_counts"]["system"] == shape["role_counts"]["user"] == 1
        assert shape["content_kind_counts"]["string"] == 1
        assert shape["content_kind_counts"]["array"] == 1
        assert shape["unknown_field_count"] == shape["message_unknown_field_count"] == 0
        assert shape["field_types"] == {
            "model": "string", "messages": "array", "stream": "boolean",
            "stream_options": "object", "tools": "array",
            "tool_choice": "string", "max_tokens": "number",
        }
    calls = []
    gate = fixture(tmp_path, lambda raw: calls.append(raw) or
                   FakeSseResponse(200, "text/event-stream", None, ((SSE, 0),)), body=body)
    if allowed:
        assert request(gate, body=body) == SSE
        with pytest.raises(FakeGatewayDenied):
            request(gate, body=body)
        assert gate.store.consumed_count() == 1
        assert calls == [body]
    else:
        with pytest.raises(FakeGatewayDenied):
            request(gate, body=body)
        assert gate.store.consumed_count() == 0
        assert calls == []


@pytest.mark.parametrize("change", [
    {"method": "GET"}, {"path": "/v1/models"},
    {"path": "/v1/chat/completions?x=1"},
    {"content_type": "text/plain"}, {"authorization": "Bearer wrong"},
    {"body": BODY + b" "}, {"body": b"x" * 65537},
    {"run_id": "other"}, {"cancelled": True}, {"revoked": True},
    {"now": "2026-10-04T00:05:00Z"},
])
def test_denied_request_never_consumes_or_calls_fake(tmp_path, change):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body))
    with pytest.raises(FakeGatewayDenied):
        request(gate, **change)
    assert gate.store.consumed_count() == 0
    assert calls == []


def test_fake_timeout_consumes_budget_without_retry(tmp_path):
    calls = []

    def timeout(body):
        calls.append(body)
        raise TimeoutError("fake timeout")

    gate = fixture(tmp_path, timeout)
    with pytest.raises(TimeoutError):
        request(gate)
    with pytest.raises(FakeGatewayDenied):
        request(gate)
    assert gate.store.consumed_count() == 1
    assert calls == [BODY]


def test_precommit_failure_never_calls_fake(tmp_path, monkeypatch):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body))

    def fail(_connection):
        raise RuntimeError("fake precommit failure")

    monkeypatch.setattr(gate.store, "_before_claim_commit", fail)
    with pytest.raises(DurableAuthorizationStoreError):
        request(gate)
    assert calls == []
    assert gate.store.consumed_count() == 0


@pytest.mark.parametrize("response", [
    FakeSseResponse(302, "text/event-stream", None, ((SSE, 0),)),
    FakeSseResponse(200, "application/json", None, ((SSE, 0),)),
    FakeSseResponse(200, "text/event-stream", None, ((b"data: {}\n\n", 0),)),
])
def test_bad_fake_stream_consumes_budget(tmp_path, response):
    gate = fixture(tmp_path, lambda body: response)
    with pytest.raises(SseResponseDenied):
        request(gate)
    with pytest.raises(FakeGatewayDenied):
        request(gate)
    assert gate.store.consumed_count() == 1


def test_identity_conflict_cannot_reissue_budget(tmp_path):
    gate = fixture(tmp_path)
    with pytest.raises(DurableAuthorizationStoreConflict):
        provision_fake_budget(gate.store, replace(gate.scope, model_binding_id="e" * 64))
    assert gate.store.consumed_count() == 0
