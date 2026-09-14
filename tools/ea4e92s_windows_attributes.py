"""Test-owned Windows attribute-list adapter; never creates a process."""

import ctypes
import os
from dataclasses import dataclass, field

from tools.ea4e92s_creation_attributes import SecurityCapabilities


ATTRIBUTE_KEYS = {"JOB_LIST": 0x0002000D, "SECURITY_CAPABILITIES": 0x00020009}
MAX_ATTRIBUTE_BYTES = 1024 * 1024


@dataclass
class NativeAttributeList:
    owner: object
    buffer: object
    keys: list = field(default_factory=list)
    values: list = field(default_factory=list)
    closed: bool = False
    failed: bool = False


class WindowsAttributeApi:
    def __init__(self, kernel32=None, last_error=None):
        if kernel32 is None:
            if os.name != "nt":
                raise OSError("Windows attribute API requires Windows")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            last_error = ctypes.get_last_error
        if not callable(last_error):
            raise ValueError("explicit error reader required for injected API")
        kernel32.InitializeProcThreadAttributeList.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_size_t)]
        kernel32.InitializeProcThreadAttributeList.restype = ctypes.c_int32
        kernel32.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
        kernel32.UpdateProcThreadAttribute.restype = ctypes.c_int32
        kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        kernel32.DeleteProcThreadAttributeList.restype = None
        self.dll = kernel32
        self.last_error = last_error

    def create(self, count):
        if type(count) is not int or count != 2:
            raise ValueError("exactly two reviewed attributes required")
        size = ctypes.c_size_t()
        probe = self.dll.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
        if probe or self.last_error() != 122 or not 0 < size.value <= MAX_ATTRIBUTE_BYTES:
            raise OSError("attribute size probe failed")
        buffer = ctypes.create_string_buffer(size.value)
        if not self.dll.InitializeProcThreadAttributeList(buffer, count, 0, ctypes.byref(size)):
            raise OSError("attribute initialization failed")
        return NativeAttributeList(self, buffer)

    def validate_owned(self, handle):
        if (type(handle) is not NativeAttributeList or handle.owner is not self
                or handle.closed or handle.failed):
            raise ValueError("attribute list is not owned and open")

    def update(self, handle, key, value):
        self.validate_owned(handle)
        expected = ("JOB_LIST", "SECURITY_CAPABILITIES")
        if len(handle.keys) >= 2 or key != expected[len(handle.keys)]:
            raise ValueError("unreviewed attribute order or key")
        if key == "JOB_LIST":
            if not (isinstance(value, ctypes.Array) and value._type_ is ctypes.c_void_p
                    and len(value) == 1 and value[0]):
                raise ValueError("one job handle required")
        elif (type(value) is not SecurityCapabilities or not value.AppContainerSid
              or value.Capabilities or value.CapabilityCount or value.Reserved):
            raise ValueError("zero-capability AppContainer descriptor required")
        handle.values.append(value)
        handle.failed = True
        applied = bool(self.dll.UpdateProcThreadAttribute(
            handle.buffer, 0, ATTRIBUTE_KEYS[key], ctypes.byref(value),
            ctypes.sizeof(value), None, None))
        if applied:
            handle.keys.append(key)
            handle.failed = False
        return applied

    def destroy(self, handle):
        if type(handle) is not NativeAttributeList or handle.owner is not self:
            raise ValueError("attribute list not owned")
        if handle.closed:
            return True
        self.dll.DeleteProcThreadAttributeList(handle.buffer)
        handle.closed = True
        handle.buffer = None
        handle.values.clear()
        return True
