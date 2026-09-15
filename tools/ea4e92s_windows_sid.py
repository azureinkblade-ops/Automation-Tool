"""Test-owned Windows SID adapter; never creates profiles, ACLs, or processes."""

import ctypes
import os


MAX_SID_BYTES = 68


class PartialSidDerivation(OSError):
    def __init__(self, message, api, pointer):
        super().__init__(message)
        self.api = api
        self.pointer = pointer


class WindowsSidApi:
    def __init__(self, userenv=None, advapi=None, reader=None):
        if (userenv is None) != (advapi is None):
            raise ValueError("both injected DLL interfaces required")
        if userenv is None:
            if os.name != "nt":
                raise OSError("Windows SID API requires Windows")
            userenv = ctypes.WinDLL("userenv", use_last_error=True)
            advapi = ctypes.WinDLL("advapi32", use_last_error=True)
            reader = ctypes.string_at
        if not callable(reader):
            raise ValueError("explicit memory reader required for injected API")

        userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
        userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
        advapi.IsValidSid.argtypes = [ctypes.c_void_p]
        advapi.IsValidSid.restype = ctypes.c_int32
        advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
        advapi.GetLengthSid.restype = ctypes.c_uint32
        advapi.FreeSid.argtypes = [ctypes.c_void_p]
        advapi.FreeSid.restype = ctypes.c_void_p
        self.userenv = userenv
        self.advapi = advapi
        self.reader = reader
        self.owned = set()
        self.validated = set()
        self.lengths = {}
        self.uncertain = set()

    def require_owned(self, pointer):
        if type(pointer) is not int or pointer not in self.owned or pointer in self.uncertain:
            raise ValueError("SID pointer is not owned and usable")

    def derive(self, profile_name):
        if type(profile_name) is not str or not profile_name or "\0" in profile_name:
            raise ValueError("explicit profile name required")
        output = ctypes.c_void_p()
        result = self.userenv.DeriveAppContainerSidFromAppContainerName(
            profile_name, ctypes.byref(output))
        pointer = output.value
        if result != 0:
            if pointer:
                self.owned.add(pointer)
                self.uncertain.add(pointer)
                raise PartialSidDerivation(
                    "SID derivation failed with allocated output", self, pointer)
            raise OSError("SID derivation failed")
        if type(pointer) is not int or pointer <= 0:
            raise OSError("SID derivation returned invalid storage")
        if pointer in self.owned:
            self.uncertain.add(pointer)
            raise PartialSidDerivation(
                "SID derivation returned duplicate storage", self, pointer)
        self.owned.add(pointer)
        return pointer

    def is_valid(self, pointer):
        self.require_owned(pointer)
        valid = bool(self.advapi.IsValidSid(pointer))
        if valid:
            self.validated.add(pointer)
        return valid

    def length(self, pointer):
        self.require_owned(pointer)
        if pointer not in self.validated:
            raise ValueError("SID validity must be established before length")
        length = self.advapi.GetLengthSid(pointer)
        if type(length) is not int or not 8 <= length <= MAX_SID_BYTES:
            raise OSError("SID length outside reviewed bounds")
        self.lengths[pointer] = length
        return length

    def read(self, pointer, length):
        self.require_owned(pointer)
        if type(length) is not int or self.lengths.get(pointer) != length:
            raise ValueError("exact validated SID length required")
        value = self.reader(pointer, length)
        if type(value) is not bytes or len(value) != length:
            raise OSError("SID memory read returned unexpected bytes")
        return value

    def free(self, pointer):
        if type(pointer) is not int or pointer not in self.owned or pointer in self.uncertain:
            raise ValueError("SID pointer is not safely releasable")
        try:
            result = self.advapi.FreeSid(pointer)
        except BaseException:
            self.uncertain.add(pointer)
            raise
        if result is not None:
            self.uncertain.add(pointer)
            return False
        self.owned.remove(pointer)
        self.validated.discard(pointer)
        self.lengths.pop(pointer, None)
        return True
