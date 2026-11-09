"""Test-owned Windows job preparation, not a process launcher or sandbox."""

import ctypes
import os
from dataclasses import dataclass


LIMIT_FLAGS = 0x00000008 | 0x00000100 | 0x00002000
JOB_MEMORY_FLAG = 0x00000200
BUILD_TREE_FLAGS = LIMIT_FLAGS | JOB_MEMORY_FLAG
PROCESS_MEMORY_BYTES = 256 * 1024 * 1024
EXTENDED_LIMITS_CLASS = 9


@dataclass(frozen=True)
class BuildxJobLimits:
    active_processes: int
    process_memory_bytes: int
    job_memory_bytes: int


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJobApi:
    """Explicit native binding; never constructed by fake-only qualification."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows job API requires Windows")
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        dll.CreateJobObjectW.restype = ctypes.c_void_p
        dll.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        dll.SetInformationJobObject.restype = ctypes.c_int32
        dll.QueryInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_void_p]
        dll.QueryInformationJobObject.restype = ctypes.c_int32
        dll.CloseHandle.argtypes = [ctypes.c_void_p]
        dll.CloseHandle.restype = ctypes.c_int32
        self.dll = dll

    def create(self):
        return self.dll.CreateJobObjectW(None, None)

    def set_limits(self, handle, limits):
        return bool(self.dll.SetInformationJobObject(
            handle, EXTENDED_LIMITS_CLASS, ctypes.byref(limits),
            ctypes.sizeof(limits)))

    def query_limits(self, handle):
        limits = ExtendedLimits()
        if not self.dll.QueryInformationJobObject(
                handle, EXTENDED_LIMITS_CLASS, ctypes.byref(limits),
                ctypes.sizeof(limits), None):
            raise OSError("job limit query failed")
        return limits

    def close(self, handle):
        return bool(self.dll.CloseHandle(handle))


class UnknownJobCleanup(RuntimeError):
    def __init__(self, message, api, handle):
        super().__init__(message)
        self.api = api
        self.handle = handle


def _prepare_job(api, *, flags, active_processes, process_memory_bytes,
                 job_memory_bytes=0):
    handle = api.create()
    if handle is None or type(handle) is not int or handle <= 0:
        raise OSError("job creation failed")
    try:
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = flags
        limits.BasicLimitInformation.ActiveProcessLimit = active_processes
        limits.ProcessMemoryLimit = process_memory_bytes
        if flags & JOB_MEMORY_FLAG:
            limits.JobMemoryLimit = job_memory_bytes
        if api.set_limits(handle, limits) is not True:
            raise OSError("job limit configuration failed")
        observed = api.query_limits(handle)
        if (type(observed) is not ExtendedLimits
                or observed.BasicLimitInformation.LimitFlags != flags
                or observed.BasicLimitInformation.ActiveProcessLimit != active_processes
                or observed.ProcessMemoryLimit != process_memory_bytes
                or (flags & JOB_MEMORY_FLAG
                    and observed.JobMemoryLimit != job_memory_bytes)):
            raise OSError("job limit verification failed")
    except BaseException:
        try:
            cleaned = api.close(handle)
        except Exception as error:
            raise UnknownJobCleanup("owned job cleanup failed", api, handle) from error
        if cleaned is not True:
            raise UnknownJobCleanup("owned job cleanup failed", api, handle)
        raise
    return handle


def prepare_job(api):
    """Return the original one-process test job; caller owns its handle.

    No process is assigned. This does not enforce network or filesystem
    isolation, a wall-clock deadline, output caps, or parser identity.
    """
    return _prepare_job(
        api, flags=LIMIT_FLAGS, active_processes=1,
        process_memory_bytes=PROCESS_MEMORY_BYTES)


def prepare_buildx_job(api, limits: BuildxJobLimits):
    """Prepare a candidate process-tree job; no process is created or assigned.

    The caller must close the owned handle. Creation-time membership, a hard
    deadline, stream bounds, plugin identity, and native enforcement remain
    separate qualifications.
    """
    if (type(limits) is not BuildxJobLimits
            or type(limits.active_processes) is not int
            or not 2 <= limits.active_processes <= 64
            or type(limits.process_memory_bytes) is not int
            or not 64 * 1024**2 <= limits.process_memory_bytes <= 2 * 1024**3
            or type(limits.job_memory_bytes) is not int
            or not limits.process_memory_bytes <= limits.job_memory_bytes <= 16 * 1024**3):
        raise ValueError("invalid Buildx job limits")
    return _prepare_job(
        api, flags=BUILD_TREE_FLAGS,
        active_processes=limits.active_processes,
        process_memory_bytes=limits.process_memory_bytes,
        job_memory_bytes=limits.job_memory_bytes)
