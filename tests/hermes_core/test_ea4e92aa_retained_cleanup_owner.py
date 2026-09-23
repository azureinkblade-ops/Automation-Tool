"""Fake-only one-shot cleanup tests for EA-4E.92AA."""

from dataclasses import replace

import pytest

from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_owned_resource_observer import OwnedResourceObservationUnknown
from tools.ea4e92s_retained_handle_registry import (
    CLEANUP_ORDER,
    RetainedHandleRegistry,
    RetainedHandleRegistryDenied,
)
from tools.ea4e92s_retained_snapshot_provider import (
    JobQuery,
    ProcessQuery,
    RetainedSnapshotProvider,
    ThreadQuery,
)
from tools import ea4e92s_retained_cleanup_owner as subject


OBSERVER = "12345678-1234-4234-8234-123456789abc"
JOB, PROCESS, THREAD = 101, 202, 303


def binding(**changes):
    value = ObserverResourceBinding(
        OBSERVER, "1" * 64, "2" * 64, "3" * 64,
        PROCESS, THREAD, 10_000, 10_001, 900)
    return replace(value, **changes)


def setup(*, fail_at=None, final_count=0):
    registry = RetainedHandleRegistry(observer_instance_id=OBSERVER)
    registry.register(
        binding(), process_id=PROCESS, thread_id=THREAD,
        job_handle=11, process_handle=22, thread_handle=33)
    events = []
    terminated = [False]

    def operation(name, result=None):
        def call(handle):
            events.append((name, handle))
            if fail_at == name:
                raise OSError("injected operation failure")
            return result(handle) if callable(result) else result
        return call

    provider = RetainedSnapshotProvider(
        registry,
        query_job=operation(
            "query_job", lambda handle: JobQuery(
                final_count if terminated[0] else 1)),
        query_process=operation(
            "query_process", lambda handle: ProcessQuery(
                PROCESS, 10_000, not terminated[0])),
        query_thread=operation(
            "query_thread", lambda handle: ThreadQuery(
                THREAD, 10_001, not terminated[0])),
        monotonic_ns=lambda: 1_000)

    def terminate(handle):
        events.append(("terminate_job", handle))
        if fail_at == "terminate_job":
            raise OSError("injected termination failure")
        terminated[0] = True
        return True

    def clock():
        events.append(("clock", None))
        if fail_at == "clock":
            raise OSError("injected clock failure")
        return 1_001

    owner = subject.RetainedCleanupOwner(
        registry, provider, terminate_job=terminate,
        close_thread=operation("close_thread", True),
        close_process=operation("close_process", True),
        close_job=operation("close_job", True),
        monotonic_ns=clock)
    return registry, provider, owner, events


def cleanup(owner, resource_binding=None):
    return owner.cleanup(
        observer_binding=resource_binding or binding(), job_id=JOB,
        process_id=PROCESS, thread_id=THREAD)


def test_cleanup_order_and_clean_tombstone_are_exact():
    registry, provider, owner, events = setup()
    result = cleanup(owner)
    assert result.binding == binding()
    assert result.cleanup_order == CLEANUP_ORDER
    assert result.active_process_count == 0
    assert result.process_present is False
    assert result.thread_present is False
    assert result.owned_handles_closed is True
    assert events == [
        ("query_job", 11), ("query_process", 22), ("query_thread", 33),
        ("terminate_job", 11),
        ("query_job", 11), ("query_process", 22), ("query_thread", 33),
        ("close_thread", 33), ("close_process", 22), ("close_job", 11),
        ("clock", None)]
    assert registry.read_tombstone(
        binding(), process_id=PROCESS, thread_id=THREAD) == result
    snapshot = provider.observe_owned_resources(
        observer_binding=binding(), job_id=JOB,
        process_id=PROCESS, thread_id=THREAD)
    assert snapshot.owned_handles_closed is True
    assert len(events) == 11


def test_exact_replay_returns_tombstone_without_repeating_operations():
    _, _, owner, events = setup()
    first = cleanup(owner)
    assert cleanup(owner) == first
    assert len(events) == 11


@pytest.mark.parametrize("fail_at", [
    "query_job", "query_process", "query_thread", "terminate_job",
    "close_thread", "close_process", "close_job", "clock",
])
def test_any_partial_failure_is_unknown_and_cannot_retry(fail_at):
    registry, provider, owner, events = setup(fail_at=fail_at)
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    count = len(events)
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    assert len(events) == count
    with pytest.raises(RetainedHandleRegistryDenied):
        registry.resolve(binding(), process_id=PROCESS, thread_id=THREAD)
    with pytest.raises(RetainedHandleRegistryDenied):
        registry.register(
            binding(), process_id=PROCESS, thread_id=THREAD,
            job_handle=11, process_handle=22, thread_handle=33)
    with pytest.raises(OwnedResourceObservationUnknown):
        provider.observe_owned_resources(
            observer_binding=binding(), job_id=JOB,
            process_id=PROCESS, thread_id=THREAD)


def test_surviving_owned_process_prevents_any_close_or_clean_claim():
    registry, _, owner, events = setup(final_count=1)
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    assert "close_thread" not in [name for name, _ in events]
    with pytest.raises(RetainedHandleRegistryDenied):
        registry.read_tombstone(
            binding(), process_id=PROCESS, thread_id=THREAD)


def test_final_query_identity_drift_prevents_close():
    _, provider, owner, events = setup()
    original = provider.query_process
    count = [0]

    def drift_on_final(handle):
        count[0] += 1
        result = original(handle)
        return replace(result, creation_time_100ns=10_002) if count[0] == 2 else result

    provider.query_process = drift_on_final
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    assert count[0] == 2
    assert "close_thread" not in [name for name, _ in events]


def test_clock_before_final_observation_is_unknown():
    registry, _, owner, _ = setup()
    owner.monotonic_ns = lambda: 999
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    with pytest.raises(RetainedHandleRegistryDenied):
        registry.read_tombstone(
            binding(), process_id=PROCESS, thread_id=THREAD)


@pytest.mark.parametrize("changes", [
    {"observer_instance_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    {"process_creation_time_100ns": 10_002},
    {"job_token_sha256": "4" * 64},
])
def test_binding_drift_denied_before_operations(changes):
    _, _, owner, events = setup()
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner, binding(**changes))
    assert events == []


def test_failed_close_confirmation_is_unknown():
    registry, _, owner, events = setup()
    owner.close_thread = lambda handle: events.append(("close_thread", handle))
    with pytest.raises(subject.RetainedCleanupUnknown):
        cleanup(owner)
    assert "close_process" not in [name for name, _ in events]
    with pytest.raises(RetainedHandleRegistryDenied):
        registry.resolve(binding(), process_id=PROCESS, thread_id=THREAD)


def test_source_has_no_native_or_launch_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "WinDLL", "OpenProcess", "OpenThread", "CloseHandle",
            "TerminateJobObject", "subprocess", "Popen", "socket",
            "requests", "ComfyUI"):
        assert forbidden not in text
