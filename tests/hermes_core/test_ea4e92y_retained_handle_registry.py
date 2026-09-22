"""Fake-only tests for the EA-4E.92Y retained-handle registry."""

from dataclasses import replace

import pytest

from tools import ea4e92s_retained_handle_registry as subject
from tools.ea4e92s_observer_identity import ObserverResourceBinding


OBSERVER = "12345678-1234-4234-8234-123456789abc"
PROCESS = 202
THREAD = 303
HANDLES = {"job_handle": 11, "process_handle": 22, "thread_handle": 33}


def binding(**changes):
    value = ObserverResourceBinding(
        OBSERVER, "1" * 64, "2" * 64, "3" * 64,
        PROCESS, THREAD, 10_000, 10_001, 900)
    return replace(value, **changes)


def tombstone(**changes):
    value = subject.CleanupTombstone(
        binding(), 1_000, subject.CLEANUP_ORDER, 0, False, False, True)
    return replace(value, **changes)


def registry():
    return subject.RetainedHandleRegistry(observer_instance_id=OBSERVER)


def register(value, resource_binding=None):
    return value.register(
        resource_binding or binding(), process_id=PROCESS, thread_id=THREAD,
        **HANDLES)


def test_register_and_resolve_exact_handles():
    value = registry()
    expected = subject.RetainedHandleResolution(binding(), 11, 22, 33)
    assert register(value) == expected
    assert value.resolve(
        binding(), process_id=PROCESS, thread_id=THREAD) == expected


def test_exact_retained_registration_replay_is_idempotent():
    value = registry()
    assert register(value) == register(value)


@pytest.mark.parametrize("changes", [
    {"job_handle": 0},
    {"process_handle": True},
    {"thread_handle": -1},
    {"thread_handle": 1 << 80},
    {"thread_handle": 22},
])
def test_malformed_or_duplicate_handles_are_denied(changes):
    value = registry()
    handles = dict(HANDLES)
    handles.update(changes)
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="handle"):
        value.register(
            binding(), process_id=PROCESS, thread_id=THREAD, **handles)


@pytest.mark.parametrize("resource_binding", [
    binding(observer_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    binding(process_id=999),
    binding(thread_id=999),
    binding(job_token_sha256="4" * 64),
])
def test_binding_drift_is_denied(resource_binding):
    value = registry()
    register(value)
    with pytest.raises(subject.RetainedHandleRegistryDenied):
        value.resolve(
            resource_binding, process_id=PROCESS, thread_id=THREAD)


def test_conflicting_registration_replay_is_denied():
    value = registry()
    register(value)
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="conflicts"):
        value.register(
            binding(), process_id=PROCESS, thread_id=THREAD,
            job_handle=11, process_handle=22, thread_handle=44)


def test_cross_binding_token_collision_is_denied():
    value = registry()
    register(value)
    conflict = binding(
        job_token_sha256="4" * 64,
        process_token_sha256="2" * 64,
        thread_token_sha256="5" * 64,
        process_creation_time_100ns=20_000)
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="token"):
        value.register(
            conflict, process_id=PROCESS, thread_id=THREAD,
            job_handle=44, process_handle=55, thread_handle=66)


def test_clean_tombstone_removes_handle_resolution():
    value = registry()
    register(value)
    assert value.seal_cleanup(
        binding(), tombstone(), process_id=PROCESS, thread_id=THREAD
    ) == tombstone()
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="cleaned"):
        value.resolve(binding(), process_id=PROCESS, thread_id=THREAD)
    assert value.read_tombstone(
        binding(), process_id=PROCESS, thread_id=THREAD) == tombstone()


def test_exact_tombstone_replay_is_idempotent_but_drift_conflicts():
    value = registry()
    register(value)
    value.seal_cleanup(
        binding(), tombstone(), process_id=PROCESS, thread_id=THREAD)
    assert value.seal_cleanup(
        binding(), tombstone(), process_id=PROCESS, thread_id=THREAD
    ) == tombstone()
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="replay"):
        value.seal_cleanup(
            binding(), tombstone(monotonic_observed_ns=1_001),
            process_id=PROCESS, thread_id=THREAD)


@pytest.mark.parametrize("changes", [
    {"monotonic_observed_ns": 899},
    {"cleanup_order": ("CLOSE_JOB",)},
    {"active_process_count": 1},
    {"active_process_count": True},
    {"process_present": True},
    {"thread_present": True},
    {"owned_handles_closed": False},
    {"owned_handles_closed": 1},
])
def test_nonclean_or_malformed_tombstone_is_denied(changes):
    value = registry()
    register(value)
    with pytest.raises(subject.RetainedHandleRegistryDenied):
        value.seal_cleanup(
            binding(), tombstone(**changes),
            process_id=PROCESS, thread_id=THREAD)
    assert value.resolve(
        binding(), process_id=PROCESS, thread_id=THREAD).job_handle == 11


def test_cleaned_registration_cannot_replay_or_reopen():
    value = registry()
    register(value)
    value.seal_cleanup(
        binding(), tombstone(), process_id=PROCESS, thread_id=THREAD)
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="cannot replay"):
        register(value)


def test_registry_loss_never_reconstructs_from_pid_or_tokens():
    first = registry()
    register(first)
    replacement = registry()
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="unavailable"):
        replacement.resolve(binding(), process_id=PROCESS, thread_id=THREAD)


@pytest.mark.parametrize("observer", ["", "UPPER", None, True])
def test_registry_requires_canonical_watcher_uuid(observer):
    with pytest.raises(subject.RetainedHandleRegistryDenied, match="observer"):
        subject.RetainedHandleRegistry(observer_instance_id=observer)


def test_source_is_memory_only_and_has_no_native_or_runtime_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "WinDLL", "OpenProcess", "QueryInformationJobObject",
            "TerminateJobObject", "CloseHandle", "subprocess", "Popen",
            "sqlite3", "json", "open(", "write_text", "socket", "requests",
            "receiver", "model", "GPU", "ComfyUI"):
        assert forbidden not in text
