"""Static Windows ABI checks with fake-owned attribute storage only."""

import ctypes
import inspect

import pytest

from tools import ea4e92s_startupinfo_abi as subject
from tools.ea4e92s_creation_attributes import prepare_creation_attributes
from tests.hermes_core.test_ea4e92s_windows_attributes import FakeKernel, adapter


def test_startupinfoex_layout_and_retained_attribute_pointer():
    api = adapter(FakeKernel())
    attributes = prepare_creation_attributes(api, 71, 91, object())
    buffer = attributes.handle.buffer
    prepared = subject.prepare_startup_info_ex(attributes)
    assert ctypes.sizeof(subject.StartupInfoW) == 104
    assert ctypes.sizeof(subject.StartupInfoExW) == 112
    assert subject.StartupInfoExW.lpAttributeList.offset == 104
    assert prepared.attributes is attributes
    assert prepared.value.StartupInfo.cb == 112
    assert prepared.value.lpAttributeList == ctypes.addressof(buffer)
    assert prepared.value.StartupInfo.dwFlags == 0
    assert prepared.value.StartupInfo.hStdInput is None
    assert prepared.value.StartupInfo.hStdOutput is None
    assert prepared.value.StartupInfo.hStdError is None
    attributes.close()


@pytest.mark.parametrize("value", [None, 0, object(), "bytes", b"bytes"])
def test_nonowner_input_denied(value):
    with pytest.raises(ValueError, match="prepared attributes"):
        subject.prepare_startup_info_ex(value)


def test_closed_or_incomplete_attribute_list_denied():
    api = adapter(FakeKernel())
    attributes = prepare_creation_attributes(api, 71, 91, object())
    attributes.handle.keys.pop()
    with pytest.raises(ValueError, match="complete owned"):
        subject.prepare_startup_info_ex(attributes)
    attributes.close()
    with pytest.raises(ValueError, match="open prepared"):
        subject.prepare_startup_info_ex(attributes)


def test_layout_module_has_no_launch_or_resume_capability():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "subprocess",
            "Popen", "socket", "requests"):
        assert forbidden not in source
