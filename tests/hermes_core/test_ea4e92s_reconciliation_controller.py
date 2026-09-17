"""Fake-observer tests for the one-shot NQ-12 reconciliation controller."""

import dataclasses

import pytest

from tools.ea4e92s_probe_evidence_store import (
    BrokerDeathObservation,
    ProbeCompletion,
    ProbeContract,
    ProbeEvidenceConflict,
    ProbeEvidenceStore,
    ProbeStart,
)
from tools.ea4e92s_reconciliation_controller import (
    ReconciliationControllerDenied,
    ReconciliationObservationUnknown,
    reconcile_broker_death,
)


CLEANUP = ("TERMINATE_JOB", "CLOSE_THREAD", "CLOSE_PROCESS", "CLOSE_JOB")


def contract(**changes):
    value = ProbeContract(
        "ea4e92s-envelope-1", "1" * 64, "2" * 64, "request-0001",
        "NQ-12", "3" * 64, "4" * 64, "5" * 64, "6" * 64,
        "HermesProbe", "7" * 64, "BROKER_DEATH_RECOVERED")
    return dataclasses.replace(value, **changes)


def unknown_store(tmp_path, **contract_changes):
    store = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    value = contract(**contract_changes)
    store.prepare(value)
    store.start(value.request_id, ProbeStart(11, 22, 33, 100, 200))
    store.complete(value.request_id, ProbeCompletion(
        "UNKNOWN", "8" * 64, 150, CLEANUP, False, 1))
    return store


class Observer:
    def __init__(self, value=None, error=None):
        self.value = value or BrokerDeathObservation(
            11, 22, 33, 160, CLEANUP, True, 0)
        self.error = error
        self.calls = []

    def observe_exact(self, **identities):
        self.calls.append(identities)
        if self.error is not None:
            raise self.error
        return self.value


def test_clean_observation_reconciles_exact_unknown(tmp_path):
    store = unknown_store(tmp_path)
    observer = Observer()
    result = reconcile_broker_death(store, "request-0001", observer)
    assert result.state == "RECONCILED_CLEAN"
    assert result.reconciliation_count == 1
    assert result.observer_called is True
    assert result.replayed is False
    assert observer.calls == [{"job_id": 11, "process_id": 22, "thread_id": 33}]


def test_nonclean_observation_remains_unknown_without_retry(tmp_path):
    store = unknown_store(tmp_path)
    observer = Observer(BrokerDeathObservation(
        11, 22, 33, 160, CLEANUP, False, 1))
    result = reconcile_broker_death(store, "request-0001", observer)
    assert result.state == "UNKNOWN"
    assert result.reconciliation_count == 1
    assert len(observer.calls) == 1


def test_later_controller_call_can_supply_newer_clean_observation(tmp_path):
    store = unknown_store(tmp_path)
    first = Observer(BrokerDeathObservation(
        11, 22, 33, 160, CLEANUP, False, 1))
    reconcile_broker_death(store, "request-0001", first)
    second = Observer(BrokerDeathObservation(
        11, 22, 33, 170, CLEANUP, True, 0))
    result = reconcile_broker_death(store, "request-0001", second)
    assert result.state == "RECONCILED_CLEAN"
    assert result.reconciliation_count == 2
    assert len(first.calls) == len(second.calls) == 1


def test_clean_replay_does_not_call_observer_again(tmp_path):
    store = unknown_store(tmp_path)
    reconcile_broker_death(store, "request-0001", Observer())
    replay_observer = Observer(error=AssertionError("must not be called"))
    result = reconcile_broker_death(store, "request-0001", replay_observer)
    assert result.replayed is True
    assert result.observer_called is False
    assert replay_observer.calls == []


@pytest.mark.parametrize("probe_id", ["NQ-01", "NQ-11"])
def test_non_broker_death_probe_is_denied_before_observation(tmp_path, probe_id):
    store = unknown_store(tmp_path, probe_id=probe_id)
    observer = Observer()
    with pytest.raises(ReconciliationControllerDenied, match="NQ-12"):
        reconcile_broker_death(store, "request-0001", observer)
    assert observer.calls == []


@pytest.mark.parametrize("state", ["PREPARED", "STARTED", "PASSED", "FAILED"])
def test_non_unknown_state_is_denied_before_observation(tmp_path, state):
    store = ProbeEvidenceStore.initialize(tmp_path / "probe.sqlite3")
    store.prepare(contract())
    if state != "PREPARED":
        store.start("request-0001", ProbeStart(11, 22, 33, 100, 200))
    if state in {"PASSED", "FAILED"}:
        store.complete("request-0001", ProbeCompletion(
            "EXPECTED" if state == "PASSED" else "UNEXPECTED",
            "8" * 64, 150, CLEANUP, True, 0))
    observer = Observer()
    with pytest.raises(ReconciliationControllerDenied, match="unknown"):
        reconcile_broker_death(store, "request-0001", observer)
    assert observer.calls == []


def test_missing_observer_boundary_keeps_unknown(tmp_path):
    store = unknown_store(tmp_path)
    with pytest.raises(ReconciliationObservationUnknown, match="unavailable"):
        reconcile_broker_death(store, "request-0001", object())
    assert store.get("request-0001").state == "UNKNOWN"


def test_observer_exception_keeps_unknown_and_is_not_retried(tmp_path):
    store = unknown_store(tmp_path)
    observer = Observer(error=OSError("scripted unavailable observation"))
    with pytest.raises(ReconciliationObservationUnknown, match="failed"):
        reconcile_broker_death(store, "request-0001", observer)
    assert len(observer.calls) == 1
    assert store.get("request-0001").state == "UNKNOWN"


@pytest.mark.parametrize("value", [None, {}, True, "clean"])
def test_malformed_observation_keeps_unknown(tmp_path, value):
    store = unknown_store(tmp_path)
    observer = Observer()
    observer.value = value
    with pytest.raises(ReconciliationObservationUnknown, match="malformed"):
        reconcile_broker_death(store, "request-0001", observer)
    assert len(observer.calls) == 1
    assert store.get("request-0001").state == "UNKNOWN"


def test_conflicting_resource_identity_is_store_denied(tmp_path):
    store = unknown_store(tmp_path)
    observer = Observer(BrokerDeathObservation(
        11, 999, 33, 160, CLEANUP, True, 0))
    with pytest.raises(ProbeEvidenceConflict, match="identity"):
        reconcile_broker_death(store, "request-0001", observer)
    assert store.get("request-0001").state == "UNKNOWN"


def test_exact_store_and_request_identity_required(tmp_path):
    store = unknown_store(tmp_path)
    observer = Observer()
    with pytest.raises(ReconciliationControllerDenied, match="store"):
        reconcile_broker_death(object(), "request-0001", observer)
    with pytest.raises(ReconciliationControllerDenied, match="request"):
        reconcile_broker_death(store, "", observer)
    assert observer.calls == []


def test_source_has_no_runtime_or_native_capability():
    from tools import ea4e92s_reconciliation_controller as subject
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "subprocess", "Popen", "WinDLL", "CreateProcessW", "OpenProcess",
            "TerminateProcess", "socket", "requests", "urlopen", "ComfyUI"):
        assert forbidden not in text
