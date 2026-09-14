import pytest

from tests.hermes_core.test_ea4e92c_provider_call_control import fixture, request, NOW
from tools.ea4e92c_provider_call_control import ProviderAdmissionDenied
from tools.ea4e92d_fake_provider_accounting import AccountedFakeProviderGate
from tools.hermes_core.production_accounting import ProductionAccountingLedger


def gate(root, forward):
    base = fixture(root, forward)
    ledger = ProductionAccountingLedger.initialize(root / "fake-accounting.sqlite3")
    return AccountedFakeProviderGate(
        base.store, base.scope, forward=forward, ledger=ledger,
        capture_path=root / "fake-response.bin", clock=lambda: NOW,
    )


def counts(value):
    return value.ledger.canonical_counts("fake-provider:" + value.scope.run_id)


def test_completed_capture_and_reopened_ledger(tmp_path):
    value = gate(tmp_path, lambda body: b"fixture response")
    assert request(value) == b"fixture response"
    assert value.capture_path.read_bytes() == b"fixture response"
    assert value.verify_capture() == b"fixture response"
    reopened = ProductionAccountingLedger(value.ledger.path)
    assert reopened.canonical_counts()["model_invocation_completed"] == 1
    assert reopened.unresolved_model_attempts() == []
    with pytest.raises(ProviderAdmissionDenied):
        request(value)
    assert counts(value)["model_invocation_entered"] == 1


def test_transport_failure_is_terminal_without_refund(tmp_path):
    calls = []

    def fail(body):
        calls.append(body)
        raise TimeoutError("fake failure")

    value = gate(tmp_path, fail)
    with pytest.raises(TimeoutError):
        request(value)
    assert counts(value)["model_invocation_failed"] == 1
    assert not value.capture_path.exists()
    with pytest.raises(ProviderAdmissionDenied):
        request(value)
    assert len(calls) == 1


@pytest.mark.parametrize("response", ["not bytes", b"x" * 65537], ids=["wrong-type", "oversized"])
def test_invalid_response_not_completed(tmp_path, response):
    value = gate(tmp_path, lambda body: response)
    with pytest.raises(ValueError):
        request(value)
    assert counts(value)["model_invocation_completed"] == 0
    assert counts(value)["model_invocation_failed"] == 1
    assert not value.capture_path.exists()


def test_existing_capture_never_overwritten(tmp_path):
    value = gate(tmp_path, lambda body: b"new")
    value.capture_path.write_bytes(b"prior")
    with pytest.raises(FileExistsError):
        request(value)
    assert value.capture_path.read_bytes() == b"prior"
    assert counts(value)["model_invocation_failed"] == 1


def test_entered_record_failure_blocks_callback(tmp_path, monkeypatch):
    calls = []
    value = gate(tmp_path, lambda body: calls.append(body) or b"ok")
    original = value.ledger.record_model_event

    def record(**kwargs):
        if kwargs["event_type"] == "MODEL_INVOCATION_ENTERED":
            raise RuntimeError("fake ledger failure")
        return original(**kwargs)

    monkeypatch.setattr(value.ledger, "record_model_event", record)
    with pytest.raises(RuntimeError, match="ledger failure"):
        request(value)
    assert calls == []
    assert value.store.consumed_count() == 1
    assert len(value.ledger.unresolved_model_attempts()) == 1


def test_interrupted_callback_stays_unresolved_and_consumed(tmp_path):
    class Interrupted(BaseException):
        pass

    def interrupt(body):
        raise Interrupted()

    value = gate(tmp_path, interrupt)
    with pytest.raises(Interrupted):
        request(value)
    reopened = ProductionAccountingLedger(value.ledger.path)
    assert len(reopened.unresolved_model_attempts()) == 1
    assert reopened.canonical_counts()["model_invocation_completed"] == 0
    with pytest.raises(ProviderAdmissionDenied):
        request(value)
    assert not value.capture_path.exists()


def test_capture_tamper_is_detected(tmp_path):
    value = gate(tmp_path, lambda body: b"original")
    request(value)
    value.capture_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        value.verify_capture()


def test_existing_manifest_never_overwritten(tmp_path):
    value = gate(tmp_path, lambda body: b"new")
    path = value.capture_path.with_suffix(".manifest.json")
    path.write_bytes(b"prior")
    with pytest.raises(FileExistsError):
        request(value)
    assert path.read_bytes() == b"prior"
    assert counts(value)["model_invocation_completed"] == 0
    assert counts(value)["model_invocation_failed"] == 1
