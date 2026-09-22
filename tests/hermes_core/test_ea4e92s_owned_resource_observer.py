"""Fake-only NQ-12 owned-resource observer contract tests."""

from dataclasses import replace

import pytest

from tools import ea4e92s_owned_resource_observer as subject
from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_probe_evidence_store import BrokerDeathObservation


JOB = 101
PROCESS = 202
THREAD = 303
OBSERVER = "12345678-1234-4234-8234-123456789abc"


def binding(**changes):
    value = ObserverResourceBinding(
        OBSERVER, "1" * 64, "2" * 64, "3" * 64,
        PROCESS, THREAD, 10_000, 10_001, 900)
    return replace(value, **changes)


def snapshot(**changes):
    value = subject.OwnedResourceSnapshot(
        JOB, PROCESS, THREAD, 1_000, subject.CLEANUP_ORDER,
        0, False, False, True)
    return replace(value, **changes)


class Provider:
    def __init__(self, value=None, error=None):
        self.value = snapshot() if value is None else value
        self.error = error
        self.calls = []

    def observe_owned_resources(self, **identities):
        self.calls.append(identities)
        if self.error is not None:
            raise self.error
        return self.value


def observe(provider):
    return subject.ExactOwnedResourceObserver(
        provider, observer_instance_id=OBSERVER).observe_exact(
            observer_binding=binding(), job_id=JOB,
            process_id=PROCESS, thread_id=THREAD)


def test_clean_snapshot_projects_exact_canonical_evidence():
    provider = Provider()
    result = observe(provider)
    assert type(result) is BrokerDeathObservation
    assert result == BrokerDeathObservation(
        JOB, PROCESS, THREAD, 1_000, subject.CLEANUP_ORDER, True, 0)
    assert provider.calls == [{
        "observer_binding": binding(), "job_id": JOB,
        "process_id": PROCESS, "thread_id": THREAD}]


@pytest.mark.parametrize("changes,survivors", [
    ({"active_process_count": 1}, 1),
    ({"process_present": True}, 0),
    ({"thread_present": True}, 0),
    ({"owned_handles_closed": False}, 0),
])
def test_nonclean_snapshot_remains_exact_unknown_evidence(changes, survivors):
    result = observe(Provider(snapshot(**changes)))
    assert result.cleanup_confirmed is False
    assert result.surviving_owned_processes == survivors


@pytest.mark.parametrize("changes", [
    {"job_id": JOB + 1},
    {"process_id": PROCESS + 1},
    {"thread_id": THREAD + 1},
])
def test_identity_drift_is_rejected(changes):
    with pytest.raises(subject.OwnedResourceObservationUnknown, match="identity"):
        observe(Provider(snapshot(**changes)))


@pytest.mark.parametrize("changes", [
    {"monotonic_observed_ns": 0},
    {"monotonic_observed_ns": True},
    {"cleanup_order": ("CLOSE_JOB",)},
    {"active_process_count": -1},
    {"active_process_count": True},
    {"process_present": 0},
    {"thread_present": 0},
    {"owned_handles_closed": 1},
])
def test_malformed_snapshot_is_rejected(changes):
    with pytest.raises(subject.OwnedResourceObservationUnknown):
        observe(Provider(snapshot(**changes)))


@pytest.mark.parametrize("identities", [
    {"job_id": 0, "process_id": PROCESS, "thread_id": THREAD},
    {"job_id": True, "process_id": PROCESS, "thread_id": THREAD},
    {"job_id": JOB, "process_id": 0, "thread_id": THREAD},
    {"job_id": JOB, "process_id": PROCESS, "thread_id": "303"},
])
def test_malformed_requested_identity_is_rejected_before_provider_call(identities):
    provider = Provider()
    observer = subject.ExactOwnedResourceObserver(
        provider, observer_instance_id=OBSERVER)
    with pytest.raises(subject.OwnedResourceObservationUnknown):
        observer.observe_exact(observer_binding=binding(), **identities)
    assert provider.calls == []


@pytest.mark.parametrize("value", [
    None,
    binding(observer_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    binding(process_id=PROCESS + 1),
    binding(thread_id=THREAD + 1),
])
def test_durable_binding_is_required_before_provider_call(value):
    provider = Provider()
    observer = subject.ExactOwnedResourceObserver(
        provider, observer_instance_id=OBSERVER)
    with pytest.raises(
            subject.OwnedResourceObservationUnknown, match="binding"):
        observer.observe_exact(
            observer_binding=value, job_id=JOB,
            process_id=PROCESS, thread_id=THREAD)
    assert provider.calls == []


def test_missing_provider_boundary_is_rejected():
    with pytest.raises(subject.OwnedResourceObservationUnknown, match="unavailable"):
        observe(object())


def test_provider_exception_is_unknown_and_never_retried():
    provider = Provider(error=OSError("scripted observation failure"))
    with pytest.raises(subject.OwnedResourceObservationUnknown, match="failed"):
        observe(provider)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("value", [None, object(), {"job_id": JOB}])
def test_noncanonical_provider_value_is_rejected(value):
    provider = Provider()
    provider.value = value
    with pytest.raises(subject.OwnedResourceObservationUnknown, match="type"):
        observe(provider)
    assert len(provider.calls) == 1


def test_source_has_no_native_or_runtime_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "WinDLL", "OpenProcess", "QueryInformationJobObject",
            "subprocess", "Popen", "socket", "requests", "browser",
            "receiver", "model", "GPU", "ComfyUI"):
        assert forbidden not in text
