"""Injected attribute-list handoff; no native creator or real process."""

import ctypes

import pytest

from tools.ea4e92s_profile_security_binding import prepare_profile_bound_security
from tools.ea4e92s_suspended_process import create_owned_suspended_process
from tests.hermes_core.test_ea4e92s_profile_security_binding import (
    FILE_ID, PATH, PIN, ProfileApi, SidApi,
)
from tests.hermes_core.test_ea4e92s_suspended_process import FakeProcessApi
from tests.hermes_core.test_ea4e92s_windows_attributes import FakeKernel, adapter


def setup():
    events = []
    kernel = FakeKernel()
    api = adapter(kernel)
    owner = prepare_profile_bound_security(
        ProfileApi(events), SidApi(events), api, 71,
        "reviewed-profile", PIN, PATH, 1234, FILE_ID)
    return owner, kernel


def test_exact_owned_native_attribute_buffer_is_passed_to_fake_creator():
    owner, kernel = setup()
    process_api = FakeProcessApi()
    owned = create_owned_suspended_process(process_api, owner)
    assert process_api.events == [
        ("create", owner.security.attributes.handle.buffer)]
    assert isinstance(process_api.events[0][1], ctypes.Array)
    assert kernel.events == ["probe", "initialize", 0x2000D, 0x20009]
    owned.close()
    owner.close()
    assert kernel.events[-1] == "delete"


@pytest.mark.parametrize("drift", [
    "missing-key", "failed", "closed", "buffer", "value", "job", "sid",
    "sid-pointer",
])
def test_attribute_drift_denies_before_fake_creation(drift):
    owner, _ = setup()
    attributes = owner.security.attributes
    handle = attributes.handle
    if drift == "missing-key":
        handle.keys.pop()
    elif drift == "failed":
        handle.failed = True
    elif drift == "closed":
        handle.closed = True
    elif drift == "buffer":
        handle.buffer = object()
    elif drift == "value":
        handle.values[0] = (ctypes.c_void_p * 1)(71)
    elif drift == "job":
        attributes.keepalive[0][0] = 0
    elif drift == "sid-pointer":
        owner.security.pointer = 0
    else:
        attributes.keepalive[1].AppContainerSid = 92
    process_api = FakeProcessApi()
    with pytest.raises(ValueError, match="reviewed native attribute list"):
        create_owned_suspended_process(process_api, owner)
    assert process_api.events == []


def test_other_attribute_api_owner_denied_before_creation():
    owner, _ = setup()
    owner.security.attributes.api = adapter(FakeKernel())
    process_api = FakeProcessApi()
    with pytest.raises(ValueError, match="reviewed native attribute list"):
        create_owned_suspended_process(process_api, owner)
    assert process_api.events == []
