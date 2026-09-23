"""Fake kernel32 qualification only; no native function is loaded or called."""

import ctypes
import inspect

import pytest

from tools import ea4e92s_windows_retained_api as subject


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeKernel32:
    def __init__(self, failure=None):
        self.events = []
        self.failure = failure
        self.QueryInformationJobObject = FakeFunction(self.job)
        self.GetProcessId = FakeFunction(self.process_id)
        self.GetThreadId = FakeFunction(self.thread_id)
        self.GetProcessTimes = FakeFunction(self.process_times)
        self.GetThreadTimes = FakeFunction(self.thread_times)
        self.WaitForSingleObject = FakeFunction(self.wait)
        self.TerminateJobObject = FakeFunction(self.terminate)
        self.CloseHandle = FakeFunction(self.close)

    def job(self, handle, info_class, output, size, unused):
        self.events.append(("job", handle))
        assert info_class == 1
        assert size == ctypes.sizeof(subject.BasicAccounting)
        if self.failure == "job":
            return 0
        ctypes.cast(output, ctypes.POINTER(subject.BasicAccounting)).contents.active_processes = 1
        return 1

    def process_id(self, handle):
        self.events.append(("pid", handle))
        return 0 if self.failure == "pid" else 203

    def thread_id(self, handle):
        self.events.append(("tid", handle))
        return 0 if self.failure == "tid" else 307

    def process_times(self, handle, creation, *_):
        self.events.append(("process_times", handle))
        ctypes.cast(creation, ctypes.POINTER(subject.FileTime)).contents.low = 11
        ctypes.cast(creation, ctypes.POINTER(subject.FileTime)).contents.high = 2
        return self.failure != "process_times"

    def thread_times(self, handle, creation, *_):
        self.events.append(("thread_times", handle))
        ctypes.cast(creation, ctypes.POINTER(subject.FileTime)).contents.low = 13
        return self.failure != "thread_times"

    def wait(self, handle, milliseconds):
        self.events.append(("wait", handle))
        assert milliseconds == 0
        return 0xFFFFFFFF if self.failure == "wait" else subject.WAIT_TIMEOUT

    def terminate(self, handle, code):
        self.events.append(("terminate", handle))
        assert code == 1
        return self.failure != "terminate"

    def close(self, handle):
        self.events.append(("close", handle))
        return self.failure != "close"


def test_fake_binding_sets_exact_signatures_without_calling_functions():
    dll = FakeKernel32()
    subject.WindowsRetainedApi(dll)
    assert dll.events == []
    for name in (
            "QueryInformationJobObject", "GetProcessId", "GetThreadId",
            "GetProcessTimes", "GetThreadTimes", "WaitForSingleObject",
            "TerminateJobObject", "CloseHandle"):
        function = getattr(dll, name)
        assert function.argtypes is not None and function.restype is not None
    assert ctypes.sizeof(subject.BasicAccounting) == 48
    assert ctypes.sizeof(subject.FileTime) == 8


def test_fake_queries_use_exact_retained_handles():
    dll = FakeKernel32()
    api = subject.WindowsRetainedApi(dll)
    assert api.query_job(101) == subject.JobQuery(1)
    assert api.query_process(102) == subject.ProcessQuery(203, (2 << 32) | 11, True)
    assert api.query_thread(103) == subject.ThreadQuery(307, 13, True)
    assert dll.events == [
        ("job", 101), ("pid", 102), ("process_times", 102),
        ("wait", 102), ("tid", 103), ("thread_times", 103),
        ("wait", 103)]


def test_fake_cleanup_calls_only_supplied_handles():
    dll = FakeKernel32()
    api = subject.WindowsRetainedApi(dll)
    assert api.terminate_job(101) is True
    assert api.close_thread(103) is True
    assert api.close_process(102) is True
    assert api.close_job(101) is True
    assert dll.events == [
        ("terminate", 101), ("close", 103), ("close", 102), ("close", 101)]


@pytest.mark.parametrize("failure,method,handle", [
    ("job", "query_job", 101),
    ("pid", "query_process", 102),
    ("process_times", "query_process", 102),
    ("tid", "query_thread", 103),
    ("thread_times", "query_thread", 103),
    ("wait", "query_process", 102),
])
def test_fake_query_failure_is_unknown(failure, method, handle):
    api = subject.WindowsRetainedApi(FakeKernel32(failure))
    with pytest.raises(OSError):
        getattr(api, method)(handle)


@pytest.mark.parametrize("failure,method", [
    ("terminate", "terminate_job"), ("close", "close_job")])
def test_fake_cleanup_failure_is_not_success(failure, method):
    api = subject.WindowsRetainedApi(FakeKernel32(failure))
    assert getattr(api, method)(101) is False


def test_no_implicit_wiring_or_process_creation():
    source = inspect.getsource(subject)
    assert "OpenProcess" not in source
    assert "OpenThread" not in source
    assert "CreateProcess" not in source
    assert "subprocess" not in source
