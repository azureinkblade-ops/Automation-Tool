"""Injected Windows API tests only; no native DLL or process is started."""

import ctypes

import pytest

from tools import ea4e92s_windows_attributes as attributes
from tools.ea4e92s_creation_attributes import UnknownAttributeCleanup
from tools.ea4e92wq_buildx_job_attributes import prepare_buildx_job_attributes


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self, *, expected_count=1, fail_update=False):
        self.expected_count = expected_count
        self.fail_update = fail_update
        self.error = 122
        self.events = []
        self.InitializeProcThreadAttributeList = Function(self.initialize)
        self.UpdateProcThreadAttribute = Function(self.update)
        self.DeleteProcThreadAttributeList = Function(self.destroy)

    def initialize(self, buffer, count, flags, size):
        assert count == self.expected_count and flags == 0
        self.events.append("probe" if buffer is None else "initialize")
        size._obj.value = 128
        return 0 if buffer is None else 1

    def update(self, buffer, flags, key, value, size, previous, returned):
        assert buffer is not None and flags == 0
        assert key == 0x2000D and size == ctypes.sizeof(value._obj)
        assert previous is returned is None
        self.events.append(key)
        return int(not self.fail_update)

    def destroy(self, buffer):
        assert buffer is not None
        self.events.append("delete")


def api(kernel):
    return attributes.WindowsAttributeApi(
        kernel, lambda: kernel.error, job_only=True)


def test_exact_job_list_is_retained_until_close():
    kernel = FakeKernel(expected_count=1)
    prepared = prepare_buildx_job_attributes(api(kernel), 71)
    assert kernel.events == ["probe", "initialize", 0x2000D]
    assert prepared.handle.keys == ["JOB_LIST"]
    assert prepared.handle.values[0] is prepared.keepalive[0]
    assert prepared.keepalive[0][0] == 71
    prepared.close()
    assert kernel.events[-1] == "delete"
    assert prepared.keepalive == ()


@pytest.mark.parametrize("job_handle", [
    None, 0, -1, True, "71", 1 << (ctypes.sizeof(ctypes.c_void_p) * 8),
])
def test_invalid_job_handle_denied_before_allocation(job_handle):
    kernel = FakeKernel(expected_count=1)
    with pytest.raises(ValueError):
        prepare_buildx_job_attributes(api(kernel), job_handle)
    assert kernel.events == []


def test_two_attribute_profile_denied_before_allocation():
    kernel = FakeKernel()
    ordinary = attributes.WindowsAttributeApi(kernel, lambda: kernel.error)
    with pytest.raises(ValueError, match="reviewed Buildx"):
        prepare_buildx_job_attributes(ordinary, 71)
    assert kernel.events == []


def test_job_only_profile_rejects_second_attribute():
    kernel = FakeKernel(expected_count=1)
    adapter = api(kernel)
    prepared = prepare_buildx_job_attributes(adapter, 71)
    with pytest.raises(ValueError, match="unreviewed"):
        adapter.update(prepared.handle, "SECURITY_CAPABILITIES", object())
    prepared.close()


def test_job_only_profile_rejects_wrong_count():
    kernel = FakeKernel(expected_count=1)
    with pytest.raises(ValueError, match="reviewed attribute count"):
        api(kernel).create(2)
    assert kernel.events == []


def test_nonboolean_attribute_profile_denied():
    kernel = FakeKernel()
    with pytest.raises(ValueError, match="attribute profile"):
        attributes.WindowsAttributeApi(kernel, lambda: kernel.error, job_only=1)
    assert kernel.events == []


def test_failed_update_closes_owned_list():
    kernel = FakeKernel(expected_count=1, fail_update=True)
    with pytest.raises(OSError, match="configuration failed"):
        prepare_buildx_job_attributes(api(kernel), 71)
    assert kernel.events == ["probe", "initialize", 0x2000D, "delete"]


def test_uncertain_delete_retains_attribute_owner():
    kernel = FakeKernel(expected_count=1)
    adapter = api(kernel)
    prepared = prepare_buildx_job_attributes(adapter, 71)

    def fail_delete(*args):
        raise OSError("scripted delete failure")

    kernel.DeleteProcThreadAttributeList.implementation = fail_delete
    with pytest.raises(UnknownAttributeCleanup) as error:
        prepared.close()
    assert error.value.prepared is prepared
    assert prepared.state == "unknown"
    assert prepared.keepalive[0][0] == 71
