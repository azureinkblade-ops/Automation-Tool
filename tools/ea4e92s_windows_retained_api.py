"""Explicit Windows bindings for watcher-retained handles; never auto-created."""

import ctypes
import os

from tools.ea4e92s_retained_snapshot_provider import (
    JobQuery,
    ProcessQuery,
    ThreadQuery,
)


WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1


class FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class BasicAccounting(ctypes.Structure):
    _fields_ = [
        ("total_user", ctypes.c_int64),
        ("total_kernel", ctypes.c_int64),
        ("period_user", ctypes.c_int64),
        ("period_kernel", ctypes.c_int64),
        ("page_faults", ctypes.c_uint32),
        ("total_processes", ctypes.c_uint32),
        ("active_processes", ctypes.c_uint32),
        ("terminated_processes", ctypes.c_uint32),
    ]


def _creation_time(value):
    return (value.high << 32) | value.low


class WindowsRetainedApi:
    """Bind exact kernel32 functions only on explicit construction."""

    def __init__(self, kernel32=None):
        if kernel32 is None:
            if os.name != "nt":
                raise OSError("Windows retained API requires Windows")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.dll = kernel32
        ptr_time = ctypes.POINTER(FileTime)
        signatures = {
            "QueryInformationJobObject": (
                [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p,
                 ctypes.c_uint32, ctypes.c_void_p], ctypes.c_int32),
            "GetProcessId": ([ctypes.c_void_p], ctypes.c_uint32),
            "GetThreadId": ([ctypes.c_void_p], ctypes.c_uint32),
            "GetProcessTimes": (
                [ctypes.c_void_p, ptr_time, ptr_time, ptr_time, ptr_time],
                ctypes.c_int32),
            "GetThreadTimes": (
                [ctypes.c_void_p, ptr_time, ptr_time, ptr_time, ptr_time],
                ctypes.c_int32),
            "WaitForSingleObject": (
                [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
            "TerminateJobObject": (
                [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int32),
            "CloseHandle": ([ctypes.c_void_p], ctypes.c_int32),
        }
        for name, (args, result) in signatures.items():
            function = getattr(kernel32, name)
            function.argtypes = args
            function.restype = result

    @staticmethod
    def _present(result):
        if result == WAIT_TIMEOUT:
            return True
        if result == WAIT_OBJECT_0:
            return False
        raise OSError("retained resource state unknown")

    def _times(self, function, handle):
        creation, exit_time, kernel, user = (
            FileTime(), FileTime(), FileTime(), FileTime())
        if not function(handle, ctypes.byref(creation), ctypes.byref(exit_time),
                        ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError("retained resource times unavailable")
        return _creation_time(creation)

    def query_job(self, handle):
        info = BasicAccounting()
        if not self.dll.QueryInformationJobObject(
                handle, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info), None):
            raise OSError("retained job accounting unavailable")
        return JobQuery(info.active_processes)

    def query_process(self, handle):
        process_id = self.dll.GetProcessId(handle)
        if not process_id:
            raise OSError("retained process identity unavailable")
        creation = self._times(self.dll.GetProcessTimes, handle)
        present = self._present(self.dll.WaitForSingleObject(handle, 0))
        return ProcessQuery(process_id, creation, present)

    def query_thread(self, handle):
        thread_id = self.dll.GetThreadId(handle)
        if not thread_id:
            raise OSError("retained thread identity unavailable")
        creation = self._times(self.dll.GetThreadTimes, handle)
        present = self._present(self.dll.WaitForSingleObject(handle, 0))
        return ThreadQuery(thread_id, creation, present)

    def terminate_job(self, handle):
        return bool(self.dll.TerminateJobObject(handle, 1))

    def close_thread(self, handle):
        return bool(self.dll.CloseHandle(handle))

    close_process = close_thread
    close_job = close_thread
