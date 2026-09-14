"""Test-owned creation-attribute composition; no native adapter or launcher."""

import ctypes
from dataclasses import dataclass


class SecurityCapabilities(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", ctypes.c_uint32),
        ("Reserved", ctypes.c_uint32),
    ]


class UnknownAttributeCleanup(RuntimeError):
    def __init__(self, message, prepared):
        super().__init__(message)
        self.prepared = prepared


@dataclass
class PreparedAttributes:
    api: object
    handle: object
    keepalive: tuple
    state: str = "owned"

    def close(self):
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownAttributeCleanup("attribute cleanup requires reconciliation", self)
        self.state = "unknown"
        try:
            if self.api.destroy(self.handle) is not True:
                raise UnknownAttributeCleanup("owned attribute cleanup failed", self)
        except Exception as error:
            raise UnknownAttributeCleanup("owned attribute cleanup failed", self) from error
        self.state = "closed"
        self.keepalive = ()


def prepare_creation_attributes(api, job_handle, sid_pointer, sid_owner):
    """Compose only reviewed job and zero-capability AppContainer attributes.

    The trusted caller must validate SID identity/storage and job limits first.
    Pointer range checks are not SID validation or proof of ownership. Symbolic
    keys must be mapped by a separately reviewed native adapter. Referenced buffers
    remain alive until the attribute list is successfully destroyed.
    """
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    for pointer in (job_handle, sid_pointer):
        if type(pointer) is not int or not 0 < pointer <= pointer_max:
            raise ValueError("invalid caller-supplied pointer")
    if sid_owner is None:
        raise ValueError("SID storage owner required")

    jobs = (ctypes.c_void_p * 1)(job_handle)
    security = SecurityCapabilities()
    security.AppContainerSid = sid_pointer
    handle = api.create(2)
    if handle is None:
        raise OSError("attribute allocation failed")
    prepared = PreparedAttributes(api, handle, (jobs, security, sid_owner))
    try:
        if api.update(handle, "JOB_LIST", jobs) is not True:
            raise OSError("job attribute configuration failed")
        if api.update(handle, "SECURITY_CAPABILITIES", security) is not True:
            raise OSError("security attribute configuration failed")
    except BaseException:
        prepared.close()
        raise
    return prepared
