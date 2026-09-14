"""Fake API tests only; no WinDLL construction or Windows job calls."""

import ctypes

import pytest

from tools import ea4e92s_windows_job as subject


class FakeApi:
    def __init__(self, failure=None, tamper=None, cleanup=True, handle=71):
        self.failure = failure
        self.tamper = tamper
        self.cleanup = cleanup
        self.handle = handle
        self.events = []

    def create(self):
        self.events.append("create")
        return self.handle

    def set_limits(self, handle, limits):
        assert handle == self.handle
        self.events.append("set")
        self.limits = subject.ExtendedLimits.from_buffer_copy(bytes(limits))
        return self.failure != "set"

    def query_limits(self, handle):
        assert handle == self.handle
        self.events.append("query")
        if self.failure == "query":
            raise OSError("scripted query failure")
        if self.tamper == "flags":
            self.limits.BasicLimitInformation.LimitFlags |= 0x800
        if self.tamper == "processes":
            self.limits.BasicLimitInformation.ActiveProcessLimit = 2
        if self.tamper == "memory":
            self.limits.ProcessMemoryLimit += 1
        return self.limits

    def close(self, handle):
        assert handle == self.handle
        self.events.append("close")
        if self.failure == "close":
            raise OSError("scripted close failure")
        return self.cleanup


def test_verified_job_stays_owned_by_caller():
    api = FakeApi()
    assert subject.prepare_job(api) == api.handle
    assert api.events == ["create", "set", "query"]
    assert api.close(api.handle) is True


@pytest.mark.parametrize("handle", [None, 0, -1, True, "71"])
def test_invalid_creation_returns_no_job(handle):
    api = FakeApi(handle=handle)
    with pytest.raises(OSError, match="creation failed"):
        subject.prepare_job(api)
    assert api.events == ["create"]


@pytest.mark.parametrize("failure", ["set", "query"])
def test_configuration_failure_closes_owned_job(failure):
    api = FakeApi(failure=failure)
    with pytest.raises(OSError):
        subject.prepare_job(api)
    assert api.events[-1] == "close"


@pytest.mark.parametrize("tamper", ["flags", "processes", "memory"])
def test_readback_drift_denied(tamper):
    api = FakeApi(tamper=tamper)
    with pytest.raises(OSError, match="verification failed"):
        subject.prepare_job(api)
    assert api.events[-1] == "close"


@pytest.mark.parametrize("cleanup", [False, None, 1])
def test_cleanup_uncertainty_is_explicit(cleanup):
    api = FakeApi(failure="set", cleanup=cleanup)
    with pytest.raises(subject.UnknownJobCleanup) as error:
        subject.prepare_job(api)
    assert error.value.api is api
    assert error.value.handle == api.handle


def test_cleanup_exception_is_explicit():
    api = FakeApi(failure="close", tamper="flags")
    with pytest.raises(subject.UnknownJobCleanup) as error:
        subject.prepare_job(api)
    assert error.value.api is api
    assert error.value.handle == api.handle


def test_win64_structure_layout():
    assert ctypes.sizeof(ctypes.c_void_p) == 8
    assert ctypes.sizeof(subject.BasicLimits) == 64
    assert ctypes.sizeof(subject.IoCounters) == 48
    assert ctypes.sizeof(subject.ExtendedLimits) == 144
    assert subject.ExtendedLimits.ProcessMemoryLimit.offset == 112
