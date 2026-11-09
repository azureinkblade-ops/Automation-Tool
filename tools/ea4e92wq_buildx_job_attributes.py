"""Test-owned Buildx job-list composition; no process creation or native call."""

import ctypes

from tools.ea4e92s_creation_attributes import PreparedAttributes
from tools.ea4e92s_windows_attributes import WindowsAttributeApi


def prepare_buildx_job_attributes(api: WindowsAttributeApi,
                                  job_handle: int) -> PreparedAttributes:
    """Retain one job handle value for a future creation-time attribute list.

    The caller owns the job and must keep its handle valid until the list is
    destroyed. This does not prove the handle belongs to a configured job.
    """
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (type(api) is not WindowsAttributeApi or api.job_only is not True
            or type(job_handle) is not int
            or not 0 < job_handle <= pointer_max):
        raise ValueError("reviewed Buildx job attribute inputs required")
    jobs = (ctypes.c_void_p * 1)(job_handle)
    handle = api.create(1)
    if handle is None:
        raise OSError("Buildx attribute allocation failed")
    prepared = PreparedAttributes(api, handle, (jobs,))
    try:
        if api.update(handle, "JOB_LIST", jobs) is not True:
            raise OSError("Buildx job attribute configuration failed")
    except BaseException:
        prepared.close()
        raise
    return prepared
