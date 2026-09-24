"""Fake-only observation tests; no native creator or resume operation."""

import ctypes
from dataclasses import replace
import inspect
from types import SimpleNamespace

import pytest

from tools import ea4e92s_provenance_observation as subject
from tools.ea4e92s_creation_provenance import (
    CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT,
    EXTENDED_STARTUPINFO_PRESENT, SuspendedCreationReceipt,
)
from tools.ea4e92s_profile_preflight import ProfileSnapshot
from tools.ea4e92s_profile_security_binding import BoundProfileSecurity
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult,
)


SID = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"
REQUEST, ADAPTER = "request-0001", "a" * 64
JOB, PROCESS, THREAD = 41, 101, 102
PID, TID = 201, 202
FLAGS = (CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
         | EXTENDED_STARTUPINFO_PRESENT)


def setup():
    profile = ProfileSnapshot(
        "reviewed-profile", SID, r"C:\reviewed-profile", 7,
        bytes(range(16)), False)
    attributes = SimpleNamespace(
        state="owned", keepalive=((ctypes.c_void_p * 1)(JOB),))
    security = SimpleNamespace(state="owned", attributes=attributes)
    owner = BoundProfileSecurity(profile, security)
    result = SuspendedCreationResult(
        PROCESS, THREAD, PID, TID, True, True, True)
    owned = OwnedSuspendedProcess(object(), result, owner)
    receipt = SuspendedCreationReceipt(
        REQUEST, ADAPTER, FLAGS, owned, owner, JOB,
        PROCESS, THREAD, PID, TID)
    return receipt, owned


class Verifier:
    def __init__(self, *, membership=True, count=1, sid=SID, failure=None):
        self.membership = membership
        self.count = count
        self.sid = sid
        self.failure = failure
        self.events = []

    def step(self, name, value):
        self.events.append(name)
        if self.failure == name:
            raise OSError("scripted query failure")
        return value

    def is_process_in_job(self, process_handle, job_handle):
        assert (process_handle, job_handle) == (PROCESS, JOB)
        return self.step("membership", self.membership)

    def active_process_count(self, job_handle):
        assert job_handle == JOB
        return self.step("count", self.count)

    def process_appcontainer_sid(self, process_handle):
        assert process_handle == PROCESS
        return self.step("sid", self.sid)

    def is_thread_suspended(self, thread_handle):
        raise AssertionError("unimplementable query must not be called")


def observe(verifier=None, receipt=None, owned=None, **changes):
    if receipt is None or owned is None:
        receipt, owned = setup()
    arguments = dict(
        request_id=REQUEST, adapter_sha256=ADAPTER,
        job_handle=JOB, expected_sid=SID)
    arguments.update(changes)
    return subject.observe_fake_pre_resume(
        verifier or Verifier(), receipt, owned, **arguments)


def test_exact_three_queries_yield_explicitly_untrusted_observation():
    verifier = Verifier()
    receipt, owned = setup()
    observed = observe(verifier, receipt, owned)
    assert type(observed) is subject.UntrustedCreationObservation
    assert observed.receipt is receipt
    assert observed.profile_name == "reviewed-profile"
    assert observed.appcontainer_sid == SID
    assert verifier.events == ["membership", "count", "sid"]
    assert not hasattr(observed, "resume_authorized")


@pytest.mark.parametrize("field,value", [
    ("creation_flags", CREATE_SUSPENDED),
    ("creation_flags", FLAGS & ~CREATE_UNICODE_ENVIRONMENT),
    ("creation_flags", FLAGS | 0x10),
    ("process_handle", THREAD),
    ("job_handle", 99),
])
def test_bad_receipt_denied_before_any_query(field, value):
    receipt, owned = setup()
    verifier = Verifier()
    with pytest.raises(subject.ProvenanceObservationDenied):
        observe(verifier, replace(receipt, **{field: value}), owned)
    assert verifier.events == []


def test_cross_request_owner_and_closed_owner_denied_before_query():
    receipt, owned = setup()
    verifier = Verifier()
    with pytest.raises(subject.ProvenanceObservationDenied):
        observe(verifier, receipt, owned, request_id="other")
    assert verifier.events == []
    owned.state = "closed"
    with pytest.raises(subject.ProvenanceObservationDenied):
        observe(verifier, receipt, owned)
    assert verifier.events == []


@pytest.mark.parametrize("value", [False, None, 1])
def test_membership_requires_exact_true_and_stops(value):
    verifier = Verifier(membership=value)
    with pytest.raises(subject.ProvenanceObservationDenied, match="membership"):
        observe(verifier)
    assert verifier.events == ["membership"]


@pytest.mark.parametrize("value", [0, 2, True, None])
def test_count_requires_exact_one_and_stops(value):
    verifier = Verifier(count=value)
    with pytest.raises(subject.ProvenanceObservationDenied, match="count"):
        observe(verifier)
    assert verifier.events == ["membership", "count"]


@pytest.mark.parametrize("value", [b"wrong", bytearray(SID), None])
def test_sid_requires_exact_bytes_and_stops(value):
    verifier = Verifier(sid=value)
    with pytest.raises(subject.ProvenanceObservationDenied, match="SID"):
        observe(verifier)
    assert verifier.events == ["membership", "count", "sid"]


@pytest.mark.parametrize("failure,events", [
    ("membership", ["membership"]),
    ("count", ["membership", "count"]),
    ("sid", ["membership", "count", "sid"]),
])
def test_query_exception_denies_without_later_queries(failure, events):
    verifier = Verifier(failure=failure)
    with pytest.raises(subject.ProvenanceObservationDenied, match="query failed"):
        observe(verifier)
    assert verifier.events == events


def test_module_has_no_native_or_resume_capability():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "SuspendThread",
            "subprocess", "resume_and_capture"):
        assert forbidden not in source
