"""Injected Win32 function tests; no native DLL is loaded."""

import ctypes

import pytest

from tools.ea4e92s_creation_attributes import prepare_creation_attributes
from tools import ea4e92s_windows_attributes as subject


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self, size=128, error=122, fail_init=False, fail_update=False):
        self.size = size
        self.error = error
        self.fail_init = fail_init
        self.fail_update = fail_update
        self.events = []
        self.InitializeProcThreadAttributeList = Function(self.initialize)
        self.UpdateProcThreadAttribute = Function(self.update)
        self.DeleteProcThreadAttributeList = Function(self.destroy)

    def initialize(self, buffer, count, flags, size):
        assert count == 2 and flags == 0
        self.events.append("probe" if buffer is None else "initialize")
        size._obj.value = self.size
        return 0 if buffer is None else int(not self.fail_init)

    def update(self, buffer, flags, key, value, size, previous, returned):
        assert flags == 0 and previous is returned is None
        assert buffer is not None and size == ctypes.sizeof(value._obj)
        self.events.append(key)
        return int(not self.fail_update)

    def destroy(self, buffer):
        assert buffer is not None
        self.events.append("delete")


def adapter(kernel):
    return subject.WindowsAttributeApi(kernel, lambda: kernel.error)


def test_composer_integrates_with_injected_native_signatures():
    kernel = FakeKernel()
    api = adapter(kernel)
    prepared = prepare_creation_attributes(api, 71, 91, object())
    assert kernel.events == ["probe", "initialize", 0x2000D, 0x20009]
    prepared.close()
    prepared.close()
    assert kernel.events[-1] == "delete"
    assert kernel.events.count("delete") == 1


@pytest.mark.parametrize("size", [0, 1024 * 1024 + 1])
def test_probe_bound_denied(size):
    kernel = FakeKernel(size=size)
    with pytest.raises(OSError, match="probe failed"):
        adapter(kernel).create(2)
    assert kernel.events == ["probe"]


def test_probe_error_denied():
    kernel = FakeKernel(error=5)
    with pytest.raises(OSError):
        adapter(kernel).create(2)
    assert kernel.events == ["probe"]


def test_initialization_failure_returns_no_list():
    kernel = FakeKernel(fail_init=True)
    with pytest.raises(OSError, match="initialization"):
        adapter(kernel).create(2)
    assert kernel.events == ["probe", "initialize"]


@pytest.mark.parametrize("count", [True, 1, 3, None])
def test_exact_count_required(count):
    kernel = FakeKernel()
    with pytest.raises(ValueError):
        adapter(kernel).create(count)
    assert kernel.events == []


def test_update_failure_cleans_initialized_list():
    kernel = FakeKernel(fail_update=True)
    with pytest.raises(OSError):
        prepare_creation_attributes(adapter(kernel), 71, 91, object())
    assert kernel.events[-1] == "delete"


def test_other_owner_denied():
    first = adapter(FakeKernel())
    second = adapter(FakeKernel())
    handle = first.create(2)
    with pytest.raises(ValueError):
        second.destroy(handle)
    assert first.destroy(handle) is True


@pytest.mark.parametrize("key", ["UNKNOWN", "SECURITY_CAPABILITIES"])
def test_unreviewed_order_denied(key):
    api = adapter(FakeKernel())
    handle = api.create(2)
    with pytest.raises(ValueError):
        api.update(handle, key, (ctypes.c_void_p * 1)(71))
    api.destroy(handle)


def test_closed_list_cannot_be_updated():
    api = adapter(FakeKernel())
    handle = api.create(2)
    api.destroy(handle)
    with pytest.raises(ValueError):
        api.update(handle, "JOB_LIST", (ctypes.c_void_p * 1)(71))


@pytest.mark.parametrize("field,value", [
    ("Capabilities", 91), ("CapabilityCount", 1), ("Reserved", 1),
    ("AppContainerSid", None)])
def test_nonzero_or_missing_security_inputs_denied(field, value):
    kernel = FakeKernel()
    api = adapter(kernel)
    handle = api.create(2)
    api.update(handle, "JOB_LIST", (ctypes.c_void_p * 1)(71))
    security = subject.SecurityCapabilities()
    security.AppContainerSid = 91
    setattr(security, field, value)
    with pytest.raises(ValueError, match="zero-capability"):
        api.update(handle, "SECURITY_CAPABILITIES", security)
    assert kernel.events == ["probe", "initialize", 0x2000D]
    api.destroy(handle)


def test_adapter_retains_value_until_deletion():
    api = adapter(FakeKernel())
    handle = api.create(2)
    jobs = (ctypes.c_void_p * 1)(71)
    api.update(handle, "JOB_LIST", jobs)
    assert handle.values == [jobs]
    api.destroy(handle)
    assert handle.values == []


def test_failed_update_retains_value_and_blocks_retry():
    api = adapter(FakeKernel(fail_update=True))
    handle = api.create(2)
    jobs = (ctypes.c_void_p * 1)(71)
    assert api.update(handle, "JOB_LIST", jobs) is False
    assert handle.values == [jobs]
    with pytest.raises(ValueError):
        api.update(handle, "JOB_LIST", jobs)
    api.destroy(handle)


def test_update_exception_retains_value_and_blocks_retry():
    kernel = FakeKernel()
    api = adapter(kernel)
    handle = api.create(2)
    def fail(*args):
        raise OSError("scripted update exception")
    kernel.UpdateProcThreadAttribute.implementation = fail
    jobs = (ctypes.c_void_p * 1)(71)
    with pytest.raises(OSError):
        api.update(handle, "JOB_LIST", jobs)
    assert handle.values == [jobs]
    with pytest.raises(ValueError):
        api.update(handle, "JOB_LIST", jobs)
    api.destroy(handle)
