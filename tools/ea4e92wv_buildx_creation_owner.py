"""Test-owned Buildx creation resources; no native launch or job call."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_creation_attributes import PreparedAttributes
from tools.ea4e92s_startupinfo_abi import PreparedStartupInfo, StartupInfoExW
from tools.ea4e92s_windows_job import OwnedBuildxJob
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult,
)
from tools.ea4e92wr_buildx_suspended_process import (
    _job_attribute_buffer, _valid_value,
)


class UnknownBuildxOwnerCleanup(RuntimeError):
    def __init__(self, owner):
        super().__init__("Buildx creation-resource cleanup requires reconciliation")
        self.owner = owner


@dataclass
class BuildxCreationOwner:
    job: OwnedBuildxJob
    attributes: PreparedAttributes
    startup: PreparedStartupInfo
    process: OwnedSuspendedProcess | None = None
    state: str = "owned"

    def attach(self, process):
        pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
        if (self.state != "owned" or self.process is not None
                or self.job.creation_owner is not self
                or self.job.state != "owned"
                or self.attributes.buildx_creation_owner is not self
                or self.attributes.state != "owned"
                or type(process) is not OwnedSuspendedProcess
                or process.state != "owned"
                or process.creation_owner is not self.attributes
                or type(process.result) is not SuspendedCreationResult
                or not _valid_value(process.result.process_handle, pointer_max)
                or not _valid_value(process.result.thread_handle, pointer_max)
                or process.result.process_handle == process.result.thread_handle
                or not _valid_value(process.result.process_id, 0xFFFFFFFF)
                or not _valid_value(process.result.thread_id, 0xFFFFFFFF)
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
            self.job.close(self)
        except Exception as error:
            raise UnknownBuildxOwnerCleanup(self) from error
        self.state = "closed"


def prepare_buildx_creation_owner(job, attributes, startup):
    """Retain a single-claim job and attributes until ordered cleanup succeeds.

    The job token comes from verified preparation; native membership is not
    proven here. A claimed job cannot be closed independently through the token.
    """
    buffer = _job_attribute_buffer(attributes)
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (type(job) is not OwnedBuildxJob or job.state != "owned"
            or job.creation_owner is not None
            or type(job.handle) is not int or not 0 < job.handle <= pointer_max
            or attributes.keepalive[0][0] != job.handle
            or not callable(getattr(job.api, "close", None))
            or type(startup) is not PreparedStartupInfo
            or startup.attributes is not attributes
            or type(startup.value) is not StartupInfoExW
            or startup.value.StartupInfo.cb != ctypes.sizeof(StartupInfoExW)
            or startup.value.lpAttributeList != ctypes.addressof(buffer)
            or attributes.buildx_creation_owner is not None):
        raise ValueError("reviewed Buildx creation resources required")
    owner = BuildxCreationOwner(job, attributes, startup)
    job.claim(owner)
    attributes.buildx_creation_owner = owner
    return owner
