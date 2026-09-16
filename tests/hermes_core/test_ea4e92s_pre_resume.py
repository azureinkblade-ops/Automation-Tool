"""Fake-only pre-resume containment verification; no process is resumed."""

import ctypes
from dataclasses import FrozenInstanceError

import pytest

from tools import ea4e92s_pre_resume as subject
from tools.ea4e92s_profile_preflight import ProfileSnapshot
from tools.ea4e92s_profile_security_binding import BoundProfileSecurity
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult)


SID = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"
FILE_ID = bytes(range(16))


class Attributes:
    def __init__(self, job_handle=41, state="owned"):
        self.state = state
        self.handle = 51
        self.keepalive = ((ctypes.c_void_p * 1)(job_handle), object(), object())


class Security:
    def __init__(self, job_handle=41, state="owned"):
        self.state = state
        self.attributes = Attributes(job_handle, state)


def owned_process(*, job_handle=41, owner_state="owned", process_state="owned",
                  profile_sid=SID, **creation_changes):
    profile = ProfileSnapshot(
        "reviewed-profile", profile_sid, r"C:\reviewed-profile", 7,
        FILE_ID, False)
    creation_owner = BoundProfileSecurity(
        profile, Security(job_handle, owner_state), owner_state)
    values = {
        "process_handle": 101, "thread_handle": 102,
        "process_id": 201, "thread_id": 202, "suspended": True,
        "job_bound_at_creation": True, "appcontainer_bound_at_creation": True,
    }
    values.update(creation_changes)
    created = SuspendedCreationResult(**values)
    return OwnedSuspendedProcess(object(), created, creation_owner, process_state)


class Verifier:
    def __init__(self, membership=True, active=1, sid=SID, suspended=True,
                 failure=None):
        self.membership = membership
        self.active = active
        self.sid = sid
        self.suspended = suspended
        self.failure = failure
        self.events = []

    def step(self, name, value, *args):
        self.events.append((name, *args))
        if self.failure == name:
            raise OSError(f"scripted {name} failure")
        return value

    def is_process_in_job(self, process_handle, job_handle):
        return self.step("membership", self.membership, process_handle, job_handle)

    def active_process_count(self, job_handle):
        return self.step("active", self.active, job_handle)

    def process_appcontainer_sid(self, process_handle):
        return self.step("sid", self.sid, process_handle)

    def is_thread_suspended(self, thread_handle):
        return self.step("suspended", self.suspended, thread_handle)


def verify(verifier=None, owned=None, job_handle=41, expected_sid=SID):
    return subject.verify_pre_resume_containment(
        verifier or Verifier(), owned or owned_process(), job_handle,
        expected_sid)


def test_exact_observations_return_immutable_bound_evidence_in_order():
    verifier = Verifier()
    evidence = verify(verifier)
    assert evidence == subject.PreResumeEvidence(
        41, 101, 102, 201, 202, "reviewed-profile", SID)
    assert [event[0] for event in verifier.events] == [
        "membership", "active", "sid", "suspended"]
    with pytest.raises(FrozenInstanceError):
        evidence.process_id = 999


@pytest.mark.parametrize("state", ["closed", "unknown", "", None])
def test_unowned_process_is_denied_before_queries(state):
    verifier = Verifier()
    with pytest.raises(ValueError, match="owned suspended process"):
        verify(verifier, owned_process(process_state=state))
    assert verifier.events == []


def test_wrong_process_owner_type_is_denied_before_queries():
    verifier = Verifier()
    with pytest.raises(ValueError, match="owned suspended process"):
        verify(verifier, object())
    assert verifier.events == []


@pytest.mark.parametrize("state", ["closed", "unknown", "", None])
def test_unowned_profile_security_is_denied_before_queries(state):
    verifier = Verifier()
    with pytest.raises(ValueError, match="owned profile security"):
        verify(verifier, owned_process(owner_state=state))
    assert verifier.events == []


@pytest.mark.parametrize("job_handle", [None, 0, -1, True, "41"])
def test_invalid_job_handle_is_denied_before_queries(job_handle):
    verifier = Verifier()
    with pytest.raises(ValueError, match="job handle"):
        verify(verifier, job_handle=job_handle)
    assert verifier.events == []


def test_job_handle_must_match_creation_attribute_binding():
    verifier = Verifier()
    with pytest.raises(ValueError, match="creation-time job binding"):
        verify(verifier, owned_process(job_handle=42))
    assert verifier.events == []


@pytest.mark.parametrize("expected", [None, b"short", bytearray(SID), "sid", b"x" * 69])
def test_invalid_expected_sid_is_denied_before_queries(expected):
    verifier = Verifier()
    with pytest.raises(ValueError, match="reviewed SID"):
        verify(verifier, expected_sid=expected)
    assert verifier.events == []


def test_expected_sid_must_match_independently_reviewed_profile():
    verifier = Verifier()
    with pytest.raises(ValueError, match="profile SID"):
        verify(verifier, owned_process(profile_sid=b"\x01" * len(SID)))
    assert verifier.events == []


@pytest.mark.parametrize("field,value", [
    ("process_handle", 0), ("process_handle", True),
    ("thread_handle", 0), ("thread_handle", True),
    ("process_id", 0), ("process_id", True),
    ("thread_id", 0), ("thread_id", True),
    ("suspended", False), ("suspended", 1),
    ("job_bound_at_creation", False), ("job_bound_at_creation", 1),
    ("appcontainer_bound_at_creation", False),
    ("appcontainer_bound_at_creation", 1),
])
def test_forged_creation_result_is_denied_before_queries(field, value):
    verifier = Verifier()
    with pytest.raises(ValueError, match="suspended creation result"):
        verify(verifier, owned_process(**{field: value}))
    assert verifier.events == []


def test_aliased_creation_handles_are_denied_before_queries():
    verifier = Verifier()
    with pytest.raises(ValueError, match="suspended creation result"):
        verify(verifier, owned_process(thread_handle=101))
    assert verifier.events == []


@pytest.mark.parametrize("value", [False, None, 1, "yes"])
def test_membership_requires_exact_true_and_stops_later_queries(value):
    verifier = Verifier(membership=value)
    with pytest.raises(subject.PreResumeDenied, match="membership"):
        verify(verifier)
    assert [event[0] for event in verifier.events] == ["membership"]


@pytest.mark.parametrize("value", [0, 2, True, None, "1"])
def test_job_requires_exactly_one_active_process(value):
    verifier = Verifier(active=value)
    with pytest.raises(subject.PreResumeDenied, match="active process"):
        verify(verifier)
    assert [event[0] for event in verifier.events] == ["membership", "active"]


@pytest.mark.parametrize("value", [None, bytearray(SID), b"wrong", "sid"])
def test_observed_appcontainer_sid_requires_exact_bytes(value):
    verifier = Verifier(sid=value)
    with pytest.raises(subject.PreResumeDenied, match="AppContainer SID"):
        verify(verifier)
    assert [event[0] for event in verifier.events] == [
        "membership", "active", "sid"]


@pytest.mark.parametrize("value", [False, None, 1, "yes"])
def test_thread_suspension_requires_exact_true(value):
    verifier = Verifier(suspended=value)
    with pytest.raises(subject.PreResumeDenied, match="suspended"):
        verify(verifier)
    assert [event[0] for event in verifier.events] == [
        "membership", "active", "sid", "suspended"]


@pytest.mark.parametrize("stage", ["membership", "active", "sid", "suspended"])
def test_query_exception_is_a_fail_closed_denial(stage):
    verifier = Verifier(failure=stage)
    with pytest.raises(subject.PreResumeDenied, match="query failed"):
        verify(verifier)
    assert verifier.events[-1][0] == stage


def test_verification_never_cleans_or_changes_owned_state():
    owned = owned_process()
    verify(owned=owned)
    assert owned.state == "owned"
    assert owned.creation_owner.state == "owned"
    assert owned.creation_owner.security.state == "owned"


def test_source_has_no_native_launch_resume_or_cleanup_capability():
    text = open(subject.__file__, encoding="utf-8").read()
    for forbidden in (
            "subprocess", "Popen", "WinDLL", "CreateProcessW", "ResumeThread",
            ".terminate(", ".close(", "socket", "requests", "ComfyUI"):
        assert forbidden not in text
