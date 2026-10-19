"""Read-only Windows token check for a future separate UAC ceremony."""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass


_SID = re.compile(r"S-[0-9]+(?:-[0-9]+){2,}\Z")
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_TOKEN_ELEVATION = 20


@dataclass(frozen=True)
class OperatorTokenCheck:
    decision: str
    reason: str


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class _TokenUser(ctypes.Structure):
    _fields_ = [("User", _SidAndAttributes)]


def _read_current_windows_token() -> tuple[str, bool]:
    if sys.platform != "win32":
        raise OSError("Windows token unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = (
        wintypes.LPVOID, ctypes.POINTER(ctypes.c_wchar_p),
    )
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        if size.value < ctypes.sizeof(_TokenUser) or size.value > 65536:
            raise OSError("Windows token user size denied")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, _TOKEN_USER, buffer, size, ctypes.byref(size),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        sid_ptr = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents.User.Sid
        sid_text = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            sid = sid_text.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, wintypes.HLOCAL))
        elevated = wintypes.DWORD()
        returned = wintypes.DWORD()
        if not advapi32.GetTokenInformation(
            token, _TOKEN_ELEVATION, ctypes.byref(elevated),
            ctypes.sizeof(elevated), ctypes.byref(returned),
        ) or returned.value != ctypes.sizeof(elevated):
            raise ctypes.WinError(ctypes.get_last_error())
        return sid, elevated.value == 1
    finally:
        kernel32.CloseHandle(token)


def check_current_windows_operator_token(expected_sid: str) -> OperatorTokenCheck:
    """Compare against a trusted policy SID; this is not authorization."""
    if type(expected_sid) is not str or not _SID.fullmatch(expected_sid):
        return OperatorTokenCheck("DENY", "EXPECTED_OPERATOR_SID_INVALID")
    try:
        sid, elevated = _read_current_windows_token()
    except (OSError, ValueError, TypeError):
        return OperatorTokenCheck("DENY", "WINDOWS_TOKEN_UNAVAILABLE")
    if type(sid) is not str or sid != expected_sid:
        return OperatorTokenCheck("DENY", "OPERATOR_SID_MISMATCH")
    if elevated is not True:
        return OperatorTokenCheck("DENY", "OPERATOR_TOKEN_NOT_ELEVATED")
    return OperatorTokenCheck("MATCH", "EXPECTED_ELEVATED_TOKEN_OBSERVED")


def read_current_windows_account_sid() -> str:
    """Observe the current process account without requiring elevation."""
    sid, _ = _read_current_windows_token()
    if type(sid) is not str or not _SID.fullmatch(sid):
        raise OSError("Windows account SID is malformed")
    return sid
