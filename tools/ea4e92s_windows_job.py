"""Test-owned Windows job preparation, not a process launcher or sandbox."""

import ctypes
import os


LIMIT_FLAGS = 0x00000008 | 0x00000100 | 0x00002000
PROCESS_MEMORY_BYTES = 256 * 1024 * 1024
EXTENDED_LIMITS_CLASS = 9


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


def prepare_job(api):
    """Return an owned configured job; caller must close it through the same API.

    No process is assigned here. Future process creation must use the reviewed
    creation-time job attribute. This layer does not enforce network/filesystem
    isolation, wall-clock limits, output caps or parser identity.
    """
    handle = api.create()
    if handle is None or type(handle) is not int or handle <= 0:
        raise OSError("job creation failed")
    try:
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = LIMIT_FLAGS
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.ProcessMemoryLimit = PROCESS_MEMORY_BYTES
        if api.set_limits(handle, limits) is not True:
            raise OSError("job limit configuration failed")
        observed = api.query_limits(handle)
        if (type(observed) is not ExtendedLimits
                or observed.BasicLimitInformation.LimitFlags != LIMIT_FLAGS
                or observed.BasicLimitInformation.ActiveProcessLimit != 1
                or observed.ProcessMemoryLimit != PROCESS_MEMORY_BYTES):
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
