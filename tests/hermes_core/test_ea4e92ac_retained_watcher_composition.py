"""Fake-only composition and one-shot watcher handoff tests."""

from dataclasses import replace

import pytest

from tools.ea4e92s_observer_identity import ObserverResourceBinding
from tools.ea4e92s_owned_resource_observer import OwnedResourceObservationUnknown
from tools.ea4e92s_retained_handle_registry import RetainedHandleRegistry
from tools.ea4e92s_retained_snapshot_provider import (
    JobQuery, ProcessQuery, ThreadQuery,
)
from tools import ea4e92s_retained_watcher_composition as subject


OBSERVER = "12345678-1234-4234-8234-123456789abc"
JOB, PROCESS, THREAD = 101, 202, 303


def binding(**changes):
    value = ObserverResourceBinding(
        OBSERVER, "1" * 64, "2" * 64, "3" * 64,
        PROCESS, THREAD, 10_000, 10_001, 900)
    return replace(value, **changes)


class FakeResources:
    def __init__(self, *, fail=None):
        self.events = []
        self.terminated = False
        self.fail = fail

    def query_job(self, handle):
        self.events.append(("job", handle))
        if self.fail == "job":
            raise OSError("query failed")
        return JobQuery(0 if self.terminated else 1)

    def query_process(self, handle):
        self.events.append(("process", handle))
        return ProcessQuery(PROCESS, 10_000, not self.terminated)

    def query_thread(self, handle):
        self.events.append(("thread", handle))
        return ThreadQuery(THREAD, 10_001, not self.terminated)

    def terminate_job(self, handle):
        self.events.append(("terminate", handle))
        if self.fail == "terminate":
            return False
        self.terminated = True
        return True

    def close_thread(self, handle):
        self.events.append(("close_thread", handle))
        return True

    def close_process(self, handle):
        self.events.append(("close_process", handle))
        return True

    def close_job(self, handle):
        self.events.append(("close_job", handle))
        return True


def setup(*, fail=None):
    registry = RetainedHandleRegistry(observer_instance_id=OBSERVER)
    registry.register(
        binding(), process_id=PROCESS, thread_id=THREAD,
        job_handle=11, process_handle=22, thread_handle=33)
    api = FakeResources(fail=fail)
    watcher = subject.compose_retained_watcher(
        registry, api, monotonic_ns=lambda: 1_000)
    return watcher, api


def args(resource_binding=None):
    return dict(
        observer_binding=resource_binding or binding(), job_id=JOB,
        process_id=PROCESS, thread_id=THREAD)


def test_composition_is_inert_until_explicit_observation():
    watcher, api = setup()
    assert api.events == []
    assert watcher.provider.registry is watcher.registry
    assert watcher.cleanup_owner.registry is watcher.registry
    assert watcher.cleanup_owner.snapshot_provider is watcher.provider
    assert watcher.observer.observer_instance_id == OBSERVER


def test_one_watcher_observes_then_cleans_and_replays_tombstone():
    watcher, api = setup()
    before = watcher.observer.observe_exact(**args())
    assert before.cleanup_confirmed is False
    assert before.surviving_owned_processes == 1
    tombstone = watcher.cleanup_owner.cleanup(**args())
    assert tombstone.owned_handles_closed is True
    assert api.events == [
        ("job", 11), ("process", 22), ("thread", 33),
        ("job", 11), ("process", 22), ("thread", 33),
        ("terminate", 11),
        ("job", 11), ("process", 22), ("thread", 33),
        ("close_thread", 33), ("close_process", 22), ("close_job", 11)]
    events = list(api.events)
    assert watcher.cleanup_owner.cleanup(**args()) == tombstone
    after = watcher.observer.observe_exact(**args())
    assert after.cleanup_confirmed is True
    assert after.surviving_owned_processes == 0
    assert api.events == events


@pytest.mark.parametrize("fail", ["job", "terminate"])
def test_unknown_operation_does_not_claim_clean_or_retry(fail):
    watcher, api = setup(fail=fail)
    with pytest.raises(Exception):
        watcher.cleanup_owner.cleanup(**args())
    events = list(api.events)
    with pytest.raises(Exception):
        watcher.cleanup_owner.cleanup(**args())
    with pytest.raises(OwnedResourceObservationUnknown):
        watcher.observer.observe_exact(**args())
    assert api.events == events


def test_wrong_binding_and_lost_registry_never_resolve_handles():
    watcher, api = setup()
    with pytest.raises(OwnedResourceObservationUnknown):
        watcher.observer.observe_exact(**args(
            binding(observer_instance_id="87654321-1234-4234-8234-123456789abc")))
    fresh = RetainedHandleRegistry(observer_instance_id=OBSERVER)
    restarted = subject.compose_retained_watcher(
        fresh, api, monotonic_ns=lambda: 1_000)
    with pytest.raises(OwnedResourceObservationUnknown):
        restarted.observer.observe_exact(**args())
    assert api.events == []


def test_incomplete_collaborators_denied_before_calls():
    registry = RetainedHandleRegistry(observer_instance_id=OBSERVER)
    with pytest.raises(ValueError):
        subject.compose_retained_watcher(registry, object(), monotonic_ns=lambda: 1)
    with pytest.raises(ValueError):
        subject.compose_retained_watcher(registry, FakeResources(), monotonic_ns=None)
    with pytest.raises(ValueError):
        subject.compose_retained_watcher(object(), FakeResources(), monotonic_ns=lambda: 1)
