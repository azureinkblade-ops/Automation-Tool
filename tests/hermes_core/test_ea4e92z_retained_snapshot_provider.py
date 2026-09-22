"""Fake-only tests for the EA-4E.92Z retained snapshot provider."""

from dataclasses import replace
from threading import Event, Thread

import pytest

from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_owned_resource_observer import (
    ExactOwnedResourceObserver,
    OwnedResourceObservationUnknown,
)
from tools.ea4e92s_retained_handle_registry import (
    CLEANUP_ORDER,
    CleanupTombstone,
    RetainedHandleRegistry,
)
from tools import ea4e92s_retained_snapshot_provider as subject


OBSERVER = "12345678-1234-4234-8234-123456789abc"
JOB, PROCESS, THREAD = 101, 202, 303


def binding(**changes):
    value = ObserverResourceBinding(
        OBSERVER, "1" * 64, "2" * 64, "3" * 64,
        PROCESS, THREAD, 10_000, 10_001, 900)
    return replace(value, **changes)


def setup(*, register=True):
    registry = RetainedHandleRegistry(observer_instance_id=OBSERVER)
    if register:
        registry.register(
            binding(), process_id=PROCESS, thread_id=THREAD,
            job_handle=11, process_handle=22, thread_handle=33)
    calls = []

    def query_job(handle):
        calls.append(("job", handle))
        return subject.JobQuery(1)

    def query_process(handle):
        calls.append(("process", handle))
        return subject.ProcessQuery(PROCESS, 10_000, True)

    def query_thread(handle):
        calls.append(("thread", handle))
        return subject.ThreadQuery(THREAD, 10_001, True)

    provider = subject.RetainedSnapshotProvider(
        registry, query_job=query_job, query_process=query_process,
        query_thread=query_thread, monotonic_ns=lambda: 1_000)
    return registry, provider, calls


def observe(provider, resource_binding=None):
    return ExactOwnedResourceObserver(
        provider, observer_instance_id=OBSERVER).observe_exact(
            observer_binding=resource_binding or binding(), job_id=JOB,
            process_id=PROCESS, thread_id=THREAD)


def test_live_query_uses_exact_retained_handles_once_and_never_claims_cleanup():
    _, provider, calls = setup()
    result = observe(provider)
    assert calls == [("job", 11), ("process", 22), ("thread", 33)]
    assert result.surviving_owned_processes == 1
    assert result.cleanup_confirmed is False
    assert result.monotonic_observed_ns == 1_000


def test_clean_tombstone_returns_without_querying_closed_handles():
    registry, provider, calls = setup()
    registry.seal_cleanup(
        binding(), CleanupTombstone(
            binding(), 1_001, CLEANUP_ORDER, 0, False, False, True),
        process_id=PROCESS, thread_id=THREAD)
    result = observe(provider)
    assert result.cleanup_confirmed is True
    assert result.monotonic_observed_ns == 1_001
    assert calls == []


def test_retained_zero_count_still_cannot_claim_handles_closed():
    _, provider, _ = setup()
    provider.query_job = lambda handle: subject.JobQuery(0)
    provider.query_process = lambda handle: subject.ProcessQuery(
        PROCESS, 10_000, False)
    provider.query_thread = lambda handle: subject.ThreadQuery(
        THREAD, 10_001, False)
    result = observe(provider)
    assert result.surviving_owned_processes == 0
    assert result.cleanup_confirmed is False


def test_cleanup_waits_for_retained_query_to_finish():
    registry, provider, _ = setup()
    entered, release, cleanup_started, cleanup_done = (
        Event(), Event(), Event(), Event())
    original = provider.query_job
    outcomes = []

    def blocked_job(handle):
        entered.set()
        assert release.wait(5)
        return original(handle)

    def cleanup():
        cleanup_started.set()
        registry.seal_cleanup(
            binding(), CleanupTombstone(
                binding(), 1_001, CLEANUP_ORDER, 0, False, False, True),
            process_id=PROCESS, thread_id=THREAD)
        cleanup_done.set()

    provider.query_job = blocked_job
    observing = Thread(target=lambda: outcomes.append(observe(provider)))
    cleaning = Thread(target=cleanup)
    try:
        observing.start()
        assert entered.wait(5)
        cleaning.start()
        assert cleanup_started.wait(5)
        assert not cleanup_done.wait(0.05)
    finally:
        release.set()
        observing.join(timeout=5)
        if cleaning.ident is not None:
            cleaning.join(timeout=5)
    assert not observing.is_alive() and not cleaning.is_alive()
    assert cleanup_done.is_set()
    assert len(outcomes) == 1 and outcomes[0].cleanup_confirmed is False


def test_lost_registry_denies_before_any_query():
    _, provider, calls = setup(register=False)
    with pytest.raises(OwnedResourceObservationUnknown):
        observe(provider)
    assert calls == []


@pytest.mark.parametrize("changes", [
    {"observer_instance_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    {"process_creation_time_100ns": 20_000},
    {"job_token_sha256": "4" * 64},
])
def test_binding_drift_denies_before_any_query(changes):
    _, provider, calls = setup()
    with pytest.raises(OwnedResourceObservationUnknown):
        observe(provider, binding(**changes))
    assert calls == []


@pytest.mark.parametrize("which,value,expected_calls", [
    ("query_job", subject.JobQuery(True), ["job"]),
    ("query_job", subject.JobQuery(-1), ["job"]),
    ("query_process", subject.ProcessQuery(999, 10_000, True),
     ["job", "process"]),
    ("query_process", subject.ProcessQuery(PROCESS, 10_002, True),
     ["job", "process"]),
    ("query_thread", subject.ThreadQuery(THREAD, 10_002, True),
     ["job", "process", "thread"]),
    ("query_thread", subject.ThreadQuery(THREAD, 10_001, 1),
     ["job", "process", "thread"]),
])
def test_malformed_or_drifted_query_stops_without_retry(
        which, value, expected_calls):
    _, provider, calls = setup()
    original = getattr(provider, which)

    def scripted(handle):
        original(handle)
        return value

    setattr(provider, which, scripted)
    with pytest.raises(OwnedResourceObservationUnknown):
        observe(provider)
    assert [name for name, _ in calls] == expected_calls


def test_query_exception_is_unknown_and_never_retried():
    _, provider, calls = setup()

    def fail(handle):
        calls.append(("job", handle))
        raise OSError("injected failure")

    provider.query_job = fail
    with pytest.raises(OwnedResourceObservationUnknown):
        observe(provider)
    assert calls == [("job", 11)]


def test_stale_clock_fails_after_one_query_sequence():
    _, provider, calls = setup()
    provider.monotonic_ns = lambda: 899
    with pytest.raises(OwnedResourceObservationUnknown):
        observe(provider)
    assert len(calls) == 3


def test_provider_source_has_no_native_or_launch_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "WinDLL", "OpenProcess", "OpenThread", "CloseHandle",
            "TerminateJobObject", "subprocess", "Popen", "socket",
            "requests", "ComfyUI"):
        assert forbidden not in text
