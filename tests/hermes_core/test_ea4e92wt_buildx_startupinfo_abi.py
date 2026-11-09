"""Injected value-only Buildx startup-info tests; no native launch."""

import ctypes

import pytest

from tools.ea4e92s_startupinfo_abi import StartupInfoExW
from tools.ea4e92s_windows_attributes import WindowsAttributeApi
from tools.ea4e92wq_buildx_job_attributes import prepare_buildx_job_attributes
from tools.ea4e92wt_buildx_startupinfo_abi import prepare_buildx_startup_info_ex


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


class FakeKernel:
    def __init__(self):
        self.InitializeProcThreadAttributeList = Function(self.initialize)
        self.UpdateProcThreadAttribute = Function(lambda *args: 1)
        self.DeleteProcThreadAttributeList = Function(lambda *args: None)

    def initialize(self, buffer, count, flags, size):
        assert count == 1 and flags == 0
        size._obj.value = 128
        return 0 if buffer is None else 1


def prepared():
    kernel = FakeKernel()
    api = WindowsAttributeApi(kernel, lambda: 122, job_only=True)
    return prepare_buildx_job_attributes(api, 71)


def test_buildx_startup_info_pins_one_job_attribute_buffer():
    attributes = prepared()
    result = prepare_buildx_startup_info_ex(attributes)
    assert type(result.value) is StartupInfoExW
    assert result.value.StartupInfo.cb == ctypes.sizeof(StartupInfoExW)
    assert result.value.lpAttributeList == ctypes.addressof(attributes.handle.buffer)
    assert result.attributes is attributes
    assert attributes.keepalive[0][0] == 71
    attributes.close()


@pytest.mark.parametrize("change", ["state", "profile", "closed", "keys", "values"])
def test_incomplete_or_unowned_attributes_denied(change):
    attributes = prepared()
    if change == "state":
        attributes.state = "unknown"
    elif change == "profile":
        attributes.api.job_only = False
    elif change == "closed":
        attributes.handle.closed = True
    elif change == "keys":
        attributes.handle.keys.clear()
    else:
        attributes.handle.values.clear()
    with pytest.raises(ValueError):
        prepare_buildx_startup_info_ex(attributes)


def test_malformed_attribute_owner_denied():
    with pytest.raises(ValueError):
        prepare_buildx_startup_info_ex(object())
