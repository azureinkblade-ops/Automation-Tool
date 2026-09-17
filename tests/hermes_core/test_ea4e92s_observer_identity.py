"""Fake-only tests for durable NQ-12 watcher-owned resource identity."""

from dataclasses import replace

import pytest

from tools import ea4e92s_observer_identity as subject


OBSERVER = "12345678-1234-5678-9234-567812345678"
PROCESS = 202
THREAD = 303
DEFAULT = object()


def binding(**changes):
    value = subject.ObserverResourceBinding(
        observer_instance_id=OBSERVER,
        job_token_sha256="1" * 64,
        process_token_sha256="2" * 64,
        thread_token_sha256="3" * 64,
        process_id=PROCESS,
        thread_id=THREAD,
        process_creation_time_100ns=10_000,
        thread_creation_time_100ns=10_001,
        binding_monotonic_ns=500,
    )
    return replace(value, **changes)


def validate(value=DEFAULT, **expected):
    return subject.validate_observer_resource_binding(
        binding() if value is DEFAULT else value,
        observer_instance_id=expected.get("observer_instance_id", OBSERVER),
        process_id=expected.get("process_id", PROCESS),
        thread_id=expected.get("thread_id", THREAD),
    )


def test_exact_binding_is_returned_unchanged():
    value = binding()
    assert validate(value) is value


@pytest.mark.parametrize("value", [None, object(), {}])
def test_noncanonical_binding_is_denied(value):
    with pytest.raises(subject.ObserverIdentityDenied, match="exact"):
        validate(value)


@pytest.mark.parametrize("value", [
    "12345678-1234-5678-9234-56781234567A",
    "{12345678-1234-5678-9234-567812345678}",
    "not-a-uuid",
    123,
])
def test_expected_observer_identity_must_be_canonical(value):
    with pytest.raises(subject.ObserverIdentityDenied, match="expected observer"):
        validate(observer_instance_id=value)


def test_observer_instance_drift_is_denied():
    with pytest.raises(subject.ObserverIdentityDenied, match="observer instance"):
        validate(binding(observer_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))


@pytest.mark.parametrize("changes", [
    {"job_token_sha256": "A" * 64},
    {"process_token_sha256": "2" * 63},
    {"thread_token_sha256": "z" * 64},
    {"process_token_sha256": "1" * 64},
])
def test_tokens_are_distinct_canonical_sha256_identities(changes):
    with pytest.raises(subject.ObserverIdentityDenied, match="tokens"):
        validate(binding(**changes))


@pytest.mark.parametrize("field,value", [
    ("process_id", 0),
    ("process_id", True),
    ("process_id", 0x100000000),
    ("thread_id", -1),
    ("thread_id", "303"),
])
def test_expected_os_identity_is_bounded(field, value):
    with pytest.raises(subject.ObserverIdentityDenied, match="expected"):
        validate(**{field: value})


@pytest.mark.parametrize("changes", [
    {"process_id": PROCESS + 1},
    {"thread_id": THREAD + 1},
])
def test_pid_or_tid_drift_is_denied(changes):
    with pytest.raises(subject.ObserverIdentityDenied, match="identity mismatch"):
        validate(binding(**changes))


@pytest.mark.parametrize("changes", [
    {"process_creation_time_100ns": 0},
    {"process_creation_time_100ns": True},
    {"thread_creation_time_100ns": -1},
    {"thread_creation_time_100ns": "10001"},
    {"binding_monotonic_ns": 0},
    {"binding_monotonic_ns": True},
])
def test_creation_and_binding_times_are_exact_positive_integers(changes):
    with pytest.raises(subject.ObserverIdentityDenied, match="malformed"):
        validate(binding(**changes))


def test_source_has_no_native_or_runtime_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "WinDLL", "OpenProcess", "DuplicateHandle", "subprocess", "Popen",
            "socket", "requests", "browser", "receiver", "model", "GPU",
            "ComfyUI"):
        assert forbidden not in text
