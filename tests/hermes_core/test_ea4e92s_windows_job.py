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
        if self.tamper == "job_memory":
            self.limits.JobMemoryLimit += 1
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


def test_original_job_ignores_inactive_total_memory_field():
    api = FakeApi(tamper="job_memory")
    assert subject.prepare_job(api) == api.handle
    assert api.events == ["create", "set", "query"]


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


def buildx_limits():
    return subject.BuildxJobLimits(4, 512 * 1024**2, 2 * 1024**3)


def test_buildx_job_verifies_process_and_total_memory_bounds():
    api = FakeApi()
    assert subject.prepare_buildx_job(api, buildx_limits()) == api.handle
    assert api.events == ["create", "set", "query"]
    assert api.limits.BasicLimitInformation.LimitFlags == subject.BUILD_TREE_FLAGS
    assert api.limits.BasicLimitInformation.ActiveProcessLimit == 4
    assert api.limits.ProcessMemoryLimit == 512 * 1024**2
    assert api.limits.JobMemoryLimit == 2 * 1024**3
    assert subject.BUILD_TREE_FLAGS & subject.JOB_MEMORY_FLAG
    assert subject.BUILD_TREE_FLAGS & 0x00002000
    assert subject.BUILD_TREE_FLAGS & (0x00000800 | 0x00001000) == 0


@pytest.mark.parametrize("limits", [
    None,
    subject.BuildxJobLimits(True, 512 * 1024**2, 2 * 1024**3),
    subject.BuildxJobLimits(1, 512 * 1024**2, 2 * 1024**3),
    subject.BuildxJobLimits(65, 512 * 1024**2, 2 * 1024**3),
    subject.BuildxJobLimits(4, True, 2 * 1024**3),
    subject.BuildxJobLimits(4, 63 * 1024**2, 2 * 1024**3),
    subject.BuildxJobLimits(4, 512 * 1024**2, 256 * 1024**2),
    subject.BuildxJobLimits(4, 512 * 1024**2, 17 * 1024**3),
])
def test_invalid_buildx_limits_denied_before_job_creation(limits):
    api = FakeApi()
    with pytest.raises(ValueError, match="invalid Buildx job limits"):
        subject.prepare_buildx_job(api, limits)
    assert api.events == []


@pytest.mark.parametrize("tamper", ["flags", "processes", "memory", "job_memory"])
def test_buildx_readback_drift_closes_job(tamper):
    api = FakeApi(tamper=tamper)
    with pytest.raises(OSError, match="verification failed"):
        subject.prepare_buildx_job(api, buildx_limits())
    assert api.events == ["create", "set", "query", "close"]


def test_buildx_cleanup_uncertainty_retains_owned_handle():
    api = FakeApi(failure="set", cleanup=False)
    with pytest.raises(subject.UnknownJobCleanup) as error:
        subject.prepare_buildx_job(api, buildx_limits())
    assert error.value.api is api
    assert error.value.handle == api.handle
    assert api.events == ["create", "set", "close"]
