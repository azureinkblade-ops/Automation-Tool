"""Value-only STARTUPINFOEXW layout; no process-creation binding."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_creation_attributes import PreparedAttributes
from tools.ea4e92s_windows_attributes import NativeAttributeList, WindowsAttributeApi


class StartupInfoW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("lpReserved", ctypes.c_void_p),
        ("lpDesktop", ctypes.c_void_p),
        ("lpTitle", ctypes.c_void_p),
        ("dwX", ctypes.c_uint32),
        ("dwY", ctypes.c_uint32),
        ("dwXSize", ctypes.c_uint32),
        ("dwYSize", ctypes.c_uint32),
        ("dwXCountChars", ctypes.c_uint32),
        ("dwYCountChars", ctypes.c_uint32),
        ("dwFillAttribute", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("wShowWindow", ctypes.c_uint16),
        ("cbReserved2", ctypes.c_uint16),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
    ]


class StartupInfoExW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", StartupInfoW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


@dataclass(frozen=True)
class PreparedStartupInfo:
    value: StartupInfoExW
    attributes: PreparedAttributes


def prepare_startup_info_ex(attributes):
    """Retain the open attribute owner; this grants no launch authority."""
    if type(attributes) is not PreparedAttributes or attributes.state != "owned":
        raise ValueError("open prepared attributes required")
    handle = attributes.handle
    if (type(attributes.api) is not WindowsAttributeApi
            or type(handle) is not NativeAttributeList
            or handle.owner is not attributes.api
            or handle.closed or handle.failed
            or not isinstance(handle.buffer, ctypes.Array)
            or handle.keys != ["JOB_LIST", "SECURITY_CAPABILITIES"]
            or len(handle.values) != 2
            or type(attributes.keepalive) is not tuple
            or len(attributes.keepalive) != 3
            or handle.values[0] is not attributes.keepalive[0]
            or handle.values[1] is not attributes.keepalive[1]):
        raise ValueError("complete owned attribute list required")
    startup = StartupInfoExW()
    startup.StartupInfo.cb = ctypes.sizeof(StartupInfoExW)
    startup.lpAttributeList = ctypes.addressof(handle.buffer)
    return PreparedStartupInfo(startup, attributes)
