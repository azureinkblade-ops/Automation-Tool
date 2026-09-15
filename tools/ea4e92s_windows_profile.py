"""Test-owned Windows profile inspector; never creates or changes a profile."""

import ctypes
import os
from dataclasses import dataclass

from tools.ea4e92s_profile_preflight import ProfileSnapshot
from tools.ea4e92s_windows_sid import PartialSidDerivation, WindowsSidApi


FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
FILE_ID_INFO_CLASS = 18
FILE_SHARE_READ_WRITE_DELETE = 7
OPEN_EXISTING = 3
PROFILE_DIRECTORY_FLAGS = 0x02000000 | 0x00200000
INVALID_HANDLE_VALUE = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1


class FileId128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class FileIdInfo(ctypes.Structure):
    _fields_ = [("VolumeSerialNumber", ctypes.c_ulonglong),
                ("FileId", FileId128)]


class FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [("FileAttributes", ctypes.c_uint32),
                ("ReparseTag", ctypes.c_uint32)]


@dataclass(frozen=True)
class InspectionResources:
    sid_pointer: object
    sid_text_pointer: object
    path_pointer: object
    directory_handle: object


class UnknownProfileInspection(RuntimeError):
    def __init__(self, message, api, resources=None):
        super().__init__(message)
        self.api = api
        self.resources = resources


class WindowsProfileApi:
    def __init__(self, sid_api=None, userenv=None, advapi=None, ole32=None,
                 kernel32=None, wide_reader=None):
        supplied = (sid_api, userenv, advapi, ole32, kernel32, wide_reader)
        if all(value is None for value in supplied):
            if os.name != "nt":
                raise OSError("Windows profile API requires Windows")
            sid_api = WindowsSidApi()
            userenv = ctypes.WinDLL("userenv", use_last_error=True)
            advapi = ctypes.WinDLL("advapi32", use_last_error=True)
            ole32 = ctypes.WinDLL("ole32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            wide_reader = ctypes.wstring_at
        elif any(value is None for value in supplied):
            raise ValueError("complete injected Windows interfaces required")
        if not callable(wide_reader):
            raise ValueError("explicit wide-string reader required")

        advapi.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        advapi.ConvertSidToStringSidW.restype = ctypes.c_int32
        userenv.GetAppContainerFolderPath.argtypes = [
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
        userenv.GetAppContainerFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.GetFileInformationByHandleEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        kernel32.GetFileInformationByHandleEx.restype = ctypes.c_int32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int32
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        self.sid_api = sid_api
        self.userenv = userenv
        self.advapi = advapi
        self.ole32 = ole32
        self.kernel32 = kernel32
        self.wide_reader = wide_reader
        self.uncertain = False
        self.uncertain_resources = None

    @staticmethod
    def _positive_pointer(value):
        return type(value) is int and 0 < value < INVALID_HANDLE_VALUE

    def _cleanup(self, resources, original_error, uncertain_names=()):
        failures = [f"uncertain {name}" for name in uncertain_names]
        if (resources.directory_handle is not None
                and "directory_handle" not in uncertain_names):
            try:
                if not self.kernel32.CloseHandle(resources.directory_handle):
                    failures.append("directory handle")
            except BaseException as error:
                failures.append(error)
        if resources.path_pointer is not None and "path_pointer" not in uncertain_names:
            try:
                self.ole32.CoTaskMemFree(resources.path_pointer)
            except BaseException as error:
                failures.append(error)
        if (resources.sid_text_pointer is not None
                and "sid_text_pointer" not in uncertain_names):
            try:
                if self.kernel32.LocalFree(resources.sid_text_pointer) is not None:
                    failures.append("SID text")
            except BaseException as error:
                failures.append(error)
        if resources.sid_pointer is not None and "sid_pointer" not in uncertain_names:
            try:
                if self.sid_api.free(resources.sid_pointer) is not True:
                    failures.append("SID")
            except BaseException as error:
                failures.append(error)
        if failures:
            self.uncertain = True
            self.uncertain_resources = resources
            error = UnknownProfileInspection(
                "profile inspection cleanup requires reconciliation",
                self, resources)
            if original_error is not None:
                raise error from original_error
            raise error

    def inspect(self, profile_name):
        if self.uncertain:
            raise UnknownProfileInspection(
                "profile inspection requires reconciliation", self,
                self.uncertain_resources)
        if type(profile_name) is not str or not profile_name or "\0" in profile_name:
            raise ValueError("explicit profile name required")

        sid_pointer = sid_text_pointer = path_pointer = directory_handle = None
        snapshot = None
        original_error = None
        uncertain_names = set()
        try:
            try:
                sid_pointer = self.sid_api.derive(profile_name)
            except PartialSidDerivation as error:
                sid_pointer = error.pointer
                uncertain_names.add("sid_pointer")
                raise
            if self.sid_api.is_valid(sid_pointer) is not True:
                raise OSError("profile derivation returned invalid SID")
            sid_length = self.sid_api.length(sid_pointer)
            sid = self.sid_api.read(sid_pointer, sid_length)

            sid_text_output = ctypes.c_void_p()
            converted = self.advapi.ConvertSidToStringSidW(
                sid_pointer, ctypes.byref(sid_text_output))
            sid_text_pointer = sid_text_output.value
            if not converted:
                if sid_text_pointer is not None:
                    uncertain_names.add("sid_text_pointer")
                raise OSError("SID string conversion failed")
            if not self._positive_pointer(sid_text_pointer):
                if sid_text_pointer is not None:
                    uncertain_names.add("sid_text_pointer")
                raise OSError("SID string conversion failed")
            sid_text = self.wide_reader(sid_text_pointer)
            if type(sid_text) is not str or not sid_text or "\0" in sid_text:
                raise OSError("SID string conversion returned malformed string")

            path_output = ctypes.c_void_p()
            folder_result = self.userenv.GetAppContainerFolderPath(
                sid_text, ctypes.byref(path_output))
            path_pointer = path_output.value
            if folder_result != 0:
                if path_pointer is not None:
                    uncertain_names.add("path_pointer")
                raise OSError("AppContainer folder lookup failed")
            if not self._positive_pointer(path_pointer):
                if path_pointer is not None:
                    uncertain_names.add("path_pointer")
                raise OSError("AppContainer folder lookup failed")
            path = self.wide_reader(path_pointer)
            if type(path) is not str or not path or "\0" in path:
                raise OSError("folder lookup returned malformed string")

            directory_handle = self.kernel32.CreateFileW(
                path, 0, FILE_SHARE_READ_WRITE_DELETE, None, OPEN_EXISTING,
                PROFILE_DIRECTORY_FLAGS, None)
            if not self._positive_pointer(directory_handle):
                directory_handle = None
                raise OSError("profile directory open failed")

            attributes = FileAttributeTagInfo()
            if not self.kernel32.GetFileInformationByHandleEx(
                    directory_handle, FILE_ATTRIBUTE_TAG_INFO_CLASS,
                    ctypes.byref(attributes), ctypes.sizeof(attributes)):
                raise OSError("profile attribute query failed")
            if not attributes.FileAttributes & FILE_ATTRIBUTE_DIRECTORY:
                raise OSError("profile path is not a directory")

            identity = FileIdInfo()
            if not self.kernel32.GetFileInformationByHandleEx(
                    directory_handle, FILE_ID_INFO_CLASS,
                    ctypes.byref(identity), ctypes.sizeof(identity)):
                raise OSError("profile identity query failed")
            snapshot = ProfileSnapshot(
                profile_name, sid, path, identity.VolumeSerialNumber,
                bytes(identity.FileId.Identifier),
                bool(attributes.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT))
        except BaseException as error:
            original_error = error

        resources = InspectionResources(
            sid_pointer, sid_text_pointer, path_pointer, directory_handle)
        self._cleanup(resources, original_error, uncertain_names)
        if original_error is not None:
            raise original_error
        return snapshot
