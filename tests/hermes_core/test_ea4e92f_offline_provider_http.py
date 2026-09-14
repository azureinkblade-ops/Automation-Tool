import pytest

from tests.hermes_core.test_ea4e92c_provider_call_control import BODY, NOW, fixture
from tests.hermes_core.test_ea4e92d_fake_provider_accounting import gate as accounted
from tools.ea4e92f_offline_provider_http import OfflineProviderHttpHandler


def handle(handler, **changes):
    values = dict(method="POST", path="/v1/chat/completions",
                  content_type="application/json", body=BODY,
                  run_id=handler.gate.scope.run_id, now=NOW)
    values.update(changes)
    return handler.handle(**values)


def test_valid_then_duplicate_is_not_forwarded(tmp_path):
    calls = []
    handler = OfflineProviderHttpHandler(accounted(tmp_path, lambda body: calls.append(body) or b"ok"))
    assert handle(handler).status == 200
    assert handler.gate.verify_capture() == b"ok"
    assert handle(handler).status == 403
    assert calls == [BODY]


@pytest.mark.parametrize("changes,status", [
    ({"path": "/other"}, 404), ({"path": "/v1/chat/completions?redirect=x"}, 404),
    ({"path": "http://other/v1/chat/completions"}, 404), ({"method": "GET"}, 405),
    ({"content_type": "text/plain"}, 415), ({"body": "not bytes"}, 400),
    ({"body": b"x" * 65537}, 413), ({"body": b"{"}, 400),
    ({"body": b"\xff"}, 400), ({"body": b"[]"}, 400),
    ({"body": b'{"model":"other","messages":[]}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":null}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[],"stream":true}'}, 400),
    ({"body": b'{"model":"fixture-model","model":"fixture-model","messages":[]}'}, 400),
    ({"body": b'{"model":"fixture-model","messages":[],"value":NaN}'}, 400),
    ({"run_id": "other"}, 403), ({"cancelled": True}, 403), ({"revoked": True}, 403),
    ({"now": "2026-09-14T00:05:00Z"}, 403),
    ({"body": BODY + b" "}, 403),
], ids=["route", "query", "absolute-url", "method", "type", "bytes", "size",
        "json", "utf8", "array", "model", "messages", "stream", "duplicates",
        "nonfinite", "run", "cancelled", "revoked", "expired", "digest"])
def test_denial_precedes_consumption_and_forwarding(tmp_path, changes, status):
    calls = []
    handler = OfflineProviderHttpHandler(fixture(tmp_path, lambda body: calls.append(body) or b"ok"))
    assert handle(handler, **changes).status == status
    assert calls == []
    assert handler.gate.store.consumed_count() == 0


def test_upstream_error_does_not_leak_or_refund(tmp_path):
    calls = []

    def fail(body):
        calls.append(body)
        raise TimeoutError("private fixture error")

    handler = OfflineProviderHttpHandler(accounted(tmp_path, fail))
    result = handle(handler)
    assert result.status == 502
    assert b"private" not in result.body
    assert handle(handler).status == 403
    assert len(calls) == 1


def test_ledger_failure_does_not_forward(tmp_path, monkeypatch):
    from tools.hermes_core.production_accounting import ProductionAccountingError
    calls = []
    handler = OfflineProviderHttpHandler(accounted(tmp_path, lambda body: calls.append(body) or b"ok"))

    def fail(**kwargs):
        raise ProductionAccountingError("fake failure")

    monkeypatch.setattr(handler.gate.ledger, "record_model_event", fail)
    assert handle(handler).status == 503
    assert calls == []
    assert handler.gate.store.consumed_count() == 1
