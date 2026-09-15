"""Fake profile/SID binding tests; no filesystem, native API, or process."""

import pytest

from tools import ea4e92s_profile_security_binding as subject
from tools.ea4e92s_profile_preflight import ProfileSnapshot, ReviewedProfile


PIN = b"\x01\x01\0\0\0\0\0\x0f\x02\0\0\0"
FILE_ID = bytes(range(16))
PATH = r"C:\Users\David\AppData\Local\Packages\Hermes.Parser"


class ProfileApi:
    def __init__(self, events, value=None):
        self.events = events
        self.value = value or ProfileSnapshot(
            "reviewed-profile", PIN, PATH, 1234, FILE_ID, False)

    def inspect(self, name):
        self.events.append("inspect")
        return self.value


class SidApi:
    def __init__(self, events, value=PIN, free=True):
        self.events, self.value, self.release = events, value, free

    def derive(self, name):
        self.events.append("derive")
        return 91

    def is_valid(self, pointer):
        self.events.append("valid")
        return True

    def length(self, pointer):
        self.events.append("length")
        return len(self.value)

    def read(self, pointer, length):
        self.events.append("read")
        return self.value

    def free(self, pointer):
        self.events.append("free")
        return self.release


class AttributeApi:
    def __init__(self, events, destroy=True):
        self.events, self.deleted = events, destroy
        self.handle = object()

    def create(self, count):
        self.events.append("create")
        return self.handle

    def update(self, handle, key, value):
        self.events.append(key)
        return True

    def destroy(self, handle):
        self.events.append("destroy")
        return self.deleted


def prepare(events, profile=None, sid=None, attributes=None, job_handle=71):
    return subject.prepare_profile_bound_security(
        profile or ProfileApi(events), sid or SidApi(events),
        attributes or AttributeApi(events), job_handle, "reviewed-profile", PIN,
        PATH, 1234, FILE_ID)


def test_profile_is_reviewed_before_sid_and_retained_until_cleanup():
    events = []
    bound = prepare(events)
    assert events == ["inspect", "derive", "valid", "length", "read", "create",
                      "JOB_LIST", "SECURITY_CAPABILITIES"]
    assert bound.profile == ReviewedProfile(
        "reviewed-profile", PIN, PATH.lower(), 1234, FILE_ID)
    assert bound.security.attributes.keepalive[-1] is bound.security
    bound.close()
    bound.close()
    assert events[-2:] == ["destroy", "free"]
    assert bound.state == "closed"


def test_profile_mismatch_stops_before_sid_derivation():
    events = []
    bad = ProfileSnapshot("other", PIN, PATH, 1234, FILE_ID, False)
    with pytest.raises(ValueError, match="reviewed identity"):
        prepare(events, profile=ProfileApi(events, bad))
    assert events == ["inspect"]


def test_sid_mismatch_stops_before_attribute_creation_and_frees_sid():
    events = []
    with pytest.raises(ValueError, match="identity mismatch"):
        prepare(events, sid=SidApi(events, value=b"b" * 12))
    assert events == ["inspect", "derive", "valid", "length", "read", "free"]


def test_attribute_cleanup_uncertainty_retains_profile_and_security_evidence():
    events = []
    bound = prepare(events, attributes=AttributeApi(events, destroy=False))
    with pytest.raises(subject.UnknownBoundCleanup) as caught:
        bound.close()
    assert caught.value.bound is bound
    assert bound.state == "unknown"
    assert bound.profile.profile_name == "reviewed-profile"
    assert bound.security.pointer == 91 and "free" not in events
    with pytest.raises(subject.UnknownBoundCleanup):
        bound.close()
    assert events.count("destroy") == 1


def test_sid_cleanup_uncertainty_retains_profile_and_blocks_retry():
    events = []
    bound = prepare(events, sid=SidApi(events, free=False))
    with pytest.raises(subject.UnknownBoundCleanup) as caught:
        bound.close()
    assert caught.value.bound is bound
    assert bound.state == "unknown" and bound.security.pointer == 91
    with pytest.raises(subject.UnknownBoundCleanup):
        bound.close()
    assert events.count("free") == 1


def test_profile_inspection_exception_is_preserved_without_sid_call():
    events = []

    class FailingProfile:
        def inspect(self, name):
            events.append("inspect")
            raise OSError("scripted inspection failure")

    with pytest.raises(OSError, match="inspection failure"):
        prepare(events, profile=FailingProfile())
    assert events == ["inspect"]


def test_unknown_wrapper_never_reenters_externally_closed_inner_owner():
    events = []
    bound = prepare(events)
    bound.state = "unknown"
    bound.security.close()
    with pytest.raises(subject.UnknownBoundCleanup) as caught:
        bound.close()
    assert caught.value.bound is bound and bound.state == "unknown"


@pytest.mark.parametrize("job_handle", [None, 0, -1, True, "71", 1 << 64])
def test_invalid_job_handle_is_rejected_before_collaborator_activity(job_handle):
    events = []
    with pytest.raises(ValueError, match="valid job handle"):
        prepare(events, job_handle=job_handle)
    assert events == []
