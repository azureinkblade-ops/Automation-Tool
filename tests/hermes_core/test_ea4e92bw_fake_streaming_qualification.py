"""Networkless one-call streaming qualification with injected SSE bytes."""

import hashlib

import pytest

from tools.ea4e92c_provider_call_control import QualificationScope, provision_budget
from tools.ea4e92bw_fake_streaming_qualification import (
    FakeSseResponse, OfflineStreamingQualificationHandler,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.production_accounting import ProductionAccountingLedger


BODY = b'{"model":"fixture-model","messages":[],"stream":true}'
NOW = "2026-09-14T00:00:01Z"
EVENT = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
DONE = b"data: [DONE]\n\n"


def response(body):
    assert body == BODY
    return FakeSseResponse(200, "text/event-stream", None,
                           ((EVENT, 0), (DONE, 1)))


def fixture(root, respond=response):
    scope = QualificationScope(
        "fake-stream-run", "a" * 40, "b" * 64, "c" * 64, "d" * 64,
        "http://127.0.0.1:1/fixture", "fixture-model",
        hashlib.sha256(BODY).hexdigest(),
        "2026-09-14T00:00:00Z", "2026-09-14T00:05:00Z",
    )
    store = DurableInvocationAuthorizationStore.initialize(
        root / "budget.sqlite3", anchor_path=root / "anchor.json",
    )
    provision_budget(store, scope)
    ledger = ProductionAccountingLedger.initialize(root / "accounting.sqlite3")
    return OfflineStreamingQualificationHandler(
        store, scope, respond=respond, ledger=ledger,
        capture_path=root / "response.bin", clock=lambda: NOW,
    )


def handle(handler, **changes):
    args = dict(method="POST", path="/v1/chat/completions",
                content_type="application/json", body=BODY,
                run_id=handler.gate.scope.run_id, now=NOW)
    args.update(changes)
    return handler.handle(**args)


def counts(handler):
    return handler.gate.ledger.canonical_counts(
        "fake-provider:" + handler.gate.scope.run_id,
    )


def test_one_claim_one_response_capture_and_replay_denial(tmp_path):
    calls = []

    def respond(body):
        calls.append(body)
        return response(body)

    handler = fixture(tmp_path, respond)
    first = handle(handler)
    assert first.status == 200
    assert first.body == EVENT + DONE
    assert handler.gate.verify_capture() == first.body
    assert handler.gate.store.consumed_count() == 1
    assert counts(handler)["model_invocation_completed"] == 1
    assert handle(handler).status == 403
    assert calls == [BODY]


@pytest.mark.parametrize("changes,status", [
    ({"path": "/other"}, 404), ({"path": "/v1/chat/completions?x=1"}, 404),
    ({"method": "GET"}, 405), ({"content_type": "text/plain"}, 415),
    ({"body": "not bytes"}, 400), ({"body": b"x" * 65537}, 413),
    ({"body": b"{"}, 400), ({"body": b"\xff"}, 400),
    ({"body": b"[]"}, 400),
    ({"body": b'{"model":"other","messages":[],"stream":true}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[],"stream":false}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[]}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[],"stream":true,"stream":true}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[],"stream":true,"x":NaN}'}, 400),
    ({"body": BODY + b" "}, 403), ({"run_id": "other"}, 403),
    ({"cancelled": True}, 403), ({"revoked": True}, 403),
    ({"now": "2026-09-14T00:05:00Z"}, 403),
])
def test_preclaim_denials_do_not_forward(tmp_path, changes, status):
    calls = []
    handler = fixture(tmp_path, lambda body: calls.append(body) or response(body))
    assert handle(handler, **changes).status == status
    assert calls == []
    assert handler.gate.store.consumed_count() == 0


@pytest.mark.parametrize("respond", [
    lambda body: FakeSseResponse(302, "text/event-stream", None, ((DONE, 0),)),
    lambda body: FakeSseResponse(200, "text/event-stream", None, ((EVENT, 0),)),
    lambda body: FakeSseResponse(200, "application/json", None, ((DONE, 0),)),
    lambda body: FakeSseResponse(200, "text/event-stream", None, ((DONE, 30001),)),
    lambda body: b"not a response envelope",
])
def test_bad_injected_response_is_failed_and_never_refunded(tmp_path, respond):
    handler = fixture(tmp_path, respond)
    assert handle(handler).status == 502
    assert handler.gate.store.consumed_count() == 1
    assert counts(handler)["model_invocation_failed"] == 1
    assert counts(handler)["model_invocation_completed"] == 0
    assert not handler.gate.capture_path.exists()
    assert handle(handler).status == 403


def test_second_call_after_callback_failure_is_denied(tmp_path):
    calls = []

    def fail(body):
        calls.append(body)
        raise TimeoutError("private upstream error")

    handler = fixture(tmp_path, fail)
    assert handle(handler).status == 502
    assert handle(handler).status == 403
    assert calls == [BODY]
    assert counts(handler)["model_invocation_failed"] == 1


def test_entered_ledger_failure_never_calls_injected_response(tmp_path, monkeypatch):
    calls = []
    handler = fixture(tmp_path, lambda body: calls.append(body) or response(body))

    def fail(**_kwargs):
        raise RuntimeError("private ledger failure")

    monkeypatch.setattr(handler.gate.ledger, "record_model_event", fail)
    assert handle(handler).status == 502
    assert calls == []
    assert handler.gate.store.consumed_count() == 1
    assert handle(handler).status == 403


def test_crash_after_claim_stays_unresolved_and_denies_replay(tmp_path):
    class Interrupted(BaseException):
        pass

    def interrupt(_body):
        raise Interrupted()

    handler = fixture(tmp_path, interrupt)
    with pytest.raises(Interrupted):
        handle(handler)
    assert handler.gate.store.consumed_count() == 1
    assert len(handler.gate.ledger.unresolved_model_attempts()) == 1
    assert handle(handler).status == 403
