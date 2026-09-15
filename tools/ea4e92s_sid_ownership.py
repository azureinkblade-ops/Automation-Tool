"""Test-owned SID/attribute ownership with injected APIs only; no native loader."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_creation_attributes import (
    UnknownAttributeCleanup, prepare_creation_attributes)


class UnknownSidCleanup(RuntimeError):
    def __init__(self, message, owned):
        super().__init__(message)
        self.owned = owned


@dataclass
class OwnedSecurity:
    api: object
    pointer: int
    attributes: object = None
    state: str = "owned"

    def close(self):
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownSidCleanup("security cleanup requires reconciliation", self)
        self.state = "unknown"
        try:
            if self.attributes is not None:
                self.attributes.close()
            if self.api.free(self.pointer) is not True:
                raise OSError("SID cleanup not confirmed")
        except BaseException as error:
            raise UnknownSidCleanup("security cleanup requires reconciliation", self) from error
        self.state = "closed"
        self.pointer = 0
        self.attributes = None


def prepare_reviewed_security(sid_api, attribute_api, job_handle, profile_name, expected_sid):
    """Verify a derived owned SID before composition, freeing attributes first.

    Injected derive must return a newly owned pointer or raise with its own
    partial-allocation evidence. is_valid must precede length/read. free returns
    exact True only after confirmed release (native FreeSid uses NULL success).
    Reviewed bytes are caller-pinned, not derived from this same API invocation.
    Derivation/equality do not prove profile existence, ACLs or token isolation.
    """
    if type(profile_name) is not str or not profile_name or "\0" in profile_name:
        raise ValueError("explicit profile name required")
    if type(expected_sid) is not bytes or not 8 <= len(expected_sid) <= 68:
        raise ValueError("bounded reviewed SID bytes required")
    pointer = sid_api.derive(profile_name)
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if type(pointer) is not int or not 0 < pointer <= pointer_max:
        raise OSError("derive returned no owned SID pointer")
    owned = OwnedSecurity(sid_api, pointer)
    try:
        if sid_api.is_valid(pointer) is not True:
            raise ValueError("derived SID invalid")
        length = sid_api.length(pointer)
        if type(length) is not int or length != len(expected_sid):
            raise ValueError("derived SID length mismatch")
        actual = sid_api.read(pointer, length)
        if type(actual) is not bytes or actual != expected_sid:
            raise ValueError("derived SID identity mismatch")
        owned.attributes = prepare_creation_attributes(
            attribute_api, job_handle, pointer, owned)
    except BaseException as error:
        # Uncertain attribute teardown still owns native references to this SID.
        if isinstance(error, UnknownAttributeCleanup):
            owned.attributes = error.prepared
            owned.state = "unknown"
            raise UnknownSidCleanup("attribute references require reconciliation", owned) from error
        owned.close()
        raise
    return owned
