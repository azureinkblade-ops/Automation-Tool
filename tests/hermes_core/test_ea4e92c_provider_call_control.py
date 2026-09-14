from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib

import pytest

from tools.ea4e92c_provider_call_control import (
    QualificationProviderGate, QualificationScope, ProviderAdmissionDenied,
    provision_budget,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore, DurableAuthorizationStoreConflict,
    DurableAuthorizationStoreUnavailable,
    DurableAuthorizationStoreIntegrityError,
)


BODY = b'{"model":"fixture-model","messages":[]}'
NOW = "2026-09-14T00:00:01Z"


def fixture(root, forward):
    scope = QualificationScope("fixture-run", "a" * 40, "b" * 64, "c" * 64,
                               "d" * 64, "http://127.0.0.1:1/fixture", "fixture-model",
                               hashlib.sha256(BODY).hexdigest(),
                               "2026-09-14T00:00:00Z", "2026-09-14T00:05:00Z")
    store = DurableInvocationAuthorizationStore.initialize(
        root / "budget.sqlite3", anchor_path=root / "anchor.json"
    )
    provision_budget(store, scope)
    return QualificationProviderGate(store, scope, forward=forward)


def request(gate, **changes):
    values = dict(run_id=gate.scope.run_id, method="POST", endpoint=gate.scope.endpoint,
                  model=gate.scope.model, body=BODY, now=NOW)
    values.update(changes)
    return gate.request(**values)


def test_valid_then_duplicate(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or b"ok")
    assert request(gate) == b"ok"
    with pytest.raises(ProviderAdmissionDenied):
        request(gate)
    assert calls == [BODY]


@pytest.mark.parametrize("change", [
    {"run_id": "other"}, {"method": "GET"}, {"endpoint": "http://other"},
    {"model": "other"}, {"body": b"other"}, {"body": "not bytes"},
    {"body": b"x" * 65537}, {"cancelled": True}, {"revoked": True},
    {"now": "2026-09-14T00:05:00Z"}, {"now": "2026-09-13T23:59:00Z"},
    {"now": "2026-09-14T00:00:01"},
])
def test_invalid_never_consumes_or_forwards(tmp_path, change):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or b"ok")
    with pytest.raises(ProviderAdmissionDenied):
        request(gate, **change)
    assert calls == []
    assert gate.store.consumed_count() == 0


def test_callback_failure_never_refunds_after_reopen(tmp_path):
    calls = []

    def fail(body):
        calls.append(body)
        raise TimeoutError("fake timeout")

    gate = fixture(tmp_path, fail)
    with pytest.raises(TimeoutError):
        request(gate)
    reopened = DurableInvocationAuthorizationStore(
        gate.store.path, anchor_path=gate.store.anchor_path
    )
    retry = QualificationProviderGate(reopened, gate.scope, forward=fail)
    with pytest.raises(ProviderAdmissionDenied):
        request(retry)
    assert calls == [BODY]


def test_concurrent_admission_one_callback(tmp_path):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or b"ok")

    def attempt(_):
        try:
            return request(gate)
        except ProviderAdmissionDenied:
            return b"denied"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(b"ok") == 1
    assert results.count(b"denied") == 3
    assert calls == [BODY]


def test_changed_binding_conflicts(tmp_path):
    gate = fixture(tmp_path, lambda body: b"ok")
    with pytest.raises(DurableAuthorizationStoreConflict):
        provision_budget(gate.store, replace(gate.scope, source_commit="e" * 40))
    assert gate.store.consumed_count() == 0


def test_missing_store_fails_closed(tmp_path):
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        DurableInvocationAuthorizationStore(tmp_path / "absent", anchor_path=tmp_path / "anchor")


def test_transport_is_required(tmp_path):
    gate = fixture(tmp_path, lambda body: b"ok")
    with pytest.raises(ProviderAdmissionDenied):
        QualificationProviderGate(gate.store, gate.scope, forward=None)


def test_precommit_failure_never_forwards(tmp_path, monkeypatch):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or b"ok")

    def crash(connection):
        raise RuntimeError("fake precommit crash")

    with monkeypatch.context() as patch:
        patch.setattr(gate.store, "_before_claim_commit", crash)
        with pytest.raises(RuntimeError, match="precommit"):
            request(gate)
    assert calls == []
    assert gate.store.consumed_count() == 0
    assert request(gate) == b"ok"
    assert calls == [BODY]


def test_postcommit_failure_never_forwards_or_reclaims(tmp_path, monkeypatch):
    calls = []
    gate = fixture(tmp_path, lambda body: calls.append(body) or b"ok")

    def crash():
        raise RuntimeError("fake postcommit crash")

    monkeypatch.setattr(gate.store, "_after_database_commit_before_anchor", crash)
    with pytest.raises(RuntimeError, match="postcommit"):
        request(gate)
    assert calls == []
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        DurableInvocationAuthorizationStore(gate.store.path, anchor_path=gate.store.anchor_path)
    assert calls == []
