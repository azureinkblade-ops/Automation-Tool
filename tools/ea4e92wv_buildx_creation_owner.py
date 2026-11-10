"""Test-owned Buildx creation resources; no native launch or job call."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_creation_attributes import PreparedAttributes
from tools.ea4e92s_startupinfo_abi import PreparedStartupInfo, StartupInfoExW
from tools.ea4e92s_suspended_process import OwnedSuspendedProcess
from tools.ea4e92wr_buildx_suspended_process import _job_attribute_buffer


class UnknownBuildxOwnerCleanup(RuntimeError):
    def __init__(self, owner):
        super().__init__("Buildx creation-resource cleanup requires reconciliation")
        self.owner = owner


@dataclass
class BuildxCreationOwner:
    job_api: object
    job_handle: int
    attributes: PreparedAttributes
    startup: PreparedStartupInfo
    process: OwnedSuspendedProcess | None = None
    state: str = "owned"

    def attach(self, process):
        if (self.state != "owned" or self.process is not None
                or type(process) is not OwnedSuspendedProcess
                or process.state != "owned"
                or process.creation_owner is not self.attributes
                or process.result.suspended is not True
                or process.result.job_bound_at_creation is not True
                or process.result.appcontainer_bound_at_creation is not False):
            raise ValueError("owned Buildx suspended process required")
        self.process = process

    def close(self):
        if self.state == "closed":
            return
        if self.state != "owned":
            raise UnknownBuildxOwnerCleanup(self)
        self.state = "unknown"
        try:
            if self.process is not None:
                self.process.close()
            self.attributes.close()
            if self.job_api.close(self.job_handle) is not True:
                raise UnknownBuildxOwnerCleanup(self)
        except Exception as error:
            raise UnknownBuildxOwnerCleanup(self) from error
        self.state = "closed"


def prepare_buildx_creation_owner(job_api, job_handle, attributes, startup):
    """Retain the supplied job and attributes until ordered cleanup succeeds.

    The job handle is caller-supplied; configuration and native membership are
    not proven here. The caller must not close it independently while owned.
    """
    buffer = _job_attribute_buffer(attributes)
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (type(job_handle) is not int or not 0 < job_handle <= pointer_max
            or attributes.keepalive[0][0] != job_handle
            or not callable(getattr(job_api, "close", None))
            or type(startup) is not PreparedStartupInfo
            or startup.attributes is not attributes
            or type(startup.value) is not StartupInfoExW
            or startup.value.StartupInfo.cb != ctypes.sizeof(StartupInfoExW)
            or startup.value.lpAttributeList != ctypes.addressof(buffer)):
        raise ValueError("reviewed Buildx creation resources required")
    return BuildxCreationOwner(job_api, job_handle, attributes, startup)
