"""Value-only Buildx STARTUPINFOEXW preparation; no process creation."""

import ctypes

from tools.ea4e92s_startupinfo_abi import PreparedStartupInfo, StartupInfoExW
from tools.ea4e92wr_buildx_suspended_process import _job_attribute_buffer


def prepare_buildx_startup_info_ex(attributes):
    """Retain a complete one-job attribute owner for a future native launch."""
    buffer = _job_attribute_buffer(attributes)
    startup = StartupInfoExW()
    startup.StartupInfo.cb = ctypes.sizeof(StartupInfoExW)
    startup.lpAttributeList = ctypes.addressof(buffer)
    return PreparedStartupInfo(startup, attributes)
