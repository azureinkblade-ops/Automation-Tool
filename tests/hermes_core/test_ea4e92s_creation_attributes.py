"""Fake composition tests; no native attributes, profiles or processes created."""

import ctypes

import pytest

from tools import ea4e92s_creation_attributes as subject


class FakeApi:
    def __init__(self, fail=None, cleanup=True):
        self.handle = object()
        self.fail = fail
        self.cleanup = cleanup
        self.events = []
        self.values = {}

    def create(self, count):
        assert count == 2
        self.events.append("create")
        return None if self.fail == "create" else self.handle

    def update(self, handle, key, value):
        assert handle is self.handle
        self.events.append(key)
        self.values[key] = value
        if self.fail == "exception":
            raise OSError("scripted failure")
        return key != self.fail

    def destroy(self, handle):
        assert handle is self.handle
        self.events.append("destroy")
        if self.fail == "destroy":
            raise OSError("scripted destroy failure")
        return self.cleanup


def test_exact_composition_and_keepalive():
    api = FakeApi()
    owner = object()
    prepared = subject.prepare_creation_attributes(api, 71, 91, owner)
    assert api.events == ["create", "JOB_LIST", "SECURITY_CAPABILITIES"]
    assert list(api.values["JOB_LIST"]) == [71]
    security = api.values["SECURITY_CAPABILITIES"]
    assert security.AppContainerSid == 91
    assert security.Capabilities is None
    assert security.CapabilityCount == security.Reserved == 0
    assert prepared.keepalive == (api.values["JOB_LIST"], security, owner)
    prepared.close()
    prepared.close()
    assert api.events.count("destroy") == 1
    assert prepared.state == "closed"
    assert prepared.keepalive == ()


@pytest.mark.parametrize("value", [None, 0, -1, True, "71", 1 << 64])
@pytest.mark.parametrize("which", ["job", "sid"])
def test_invalid_pointers_deny_before_allocation(value, which):
    api = FakeApi()
    with pytest.raises(ValueError):
        subject.prepare_creation_attributes(
            api, value if which == "job" else 71,
            value if which == "sid" else 91, object())
    assert api.events == []


def test_storage_owner_required():
    api = FakeApi()
    with pytest.raises(ValueError, match="owner required"):
        subject.prepare_creation_attributes(api, 71, 91, None)
    assert api.events == []


def test_allocation_failure_returns_no_attributes():
    api = FakeApi(fail="create")
    with pytest.raises(OSError, match="allocation"):
        subject.prepare_creation_attributes(api, 71, 91, object())
    assert api.events == ["create"]


@pytest.mark.parametrize("failure", ["JOB_LIST", "SECURITY_CAPABILITIES", "exception"])
def test_partial_update_cleanup(failure):
    api = FakeApi(fail=failure)
    with pytest.raises(OSError):
        subject.prepare_creation_attributes(api, 71, 91, object())
    assert api.events[-1] == "destroy"


@pytest.mark.parametrize("cleanup", [False, None, 1])
def test_cleanup_uncertainty_retains_buffers_and_no_retry(cleanup):
    api = FakeApi(cleanup=cleanup)
    prepared = subject.prepare_creation_attributes(api, 71, 91, object())
    with pytest.raises(subject.UnknownAttributeCleanup):
        prepared.close()
    assert prepared.keepalive
    assert prepared.state == "unknown"
    with pytest.raises(subject.UnknownAttributeCleanup, match="reconciliation"):
        prepared.close()
    assert api.events.count("destroy") == 1


def test_cleanup_exception_is_explicit():
    api = FakeApi(fail="destroy")
    prepared = subject.prepare_creation_attributes(api, 71, 91, object())
    with pytest.raises(subject.UnknownAttributeCleanup):
        prepared.close()
    assert prepared.state == "unknown"


def test_partial_failure_keeps_owned_buffers_on_exception():
    api = FakeApi(fail="SECURITY_CAPABILITIES", cleanup=False)
    owner = object()
    with pytest.raises(subject.UnknownAttributeCleanup) as error:
        subject.prepare_creation_attributes(api, 71, 91, owner)
    assert error.value.prepared.keepalive[-1] is owner
    assert error.value.prepared.state == "unknown"


def test_security_structure_layout():
    assert ctypes.sizeof(ctypes.c_void_p) == 8
    assert ctypes.sizeof(subject.SecurityCapabilities) == 24
    assert subject.SecurityCapabilities.CapabilityCount.offset == 16
