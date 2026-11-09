"""Test-owned Buildx suspended-process handoff; no native launcher."""

import ctypes

from tools.ea4e92s_creation_attributes import PreparedAttributes
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult, SuspendedProcessDenied,
    UnknownSuspendedProcess,
)
from tools.ea4e92s_windows_attributes import NativeAttributeList, WindowsAttributeApi


def _valid_value(value, maximum):
    return type(value) is int and 0 < value <= maximum


def _job_attribute_buffer(prepared):
    if type(prepared) is not PreparedAttributes or prepared.state != "owned":
        raise ValueError("owned Buildx attributes required")
    handle = prepared.handle
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (type(prepared.api) is not WindowsAttributeApi
            or prepared.api.job_only is not True
            or type(handle) is not NativeAttributeList
            or handle.owner is not prepared.api
            or handle.closed or handle.failed
            or not isinstance(handle.buffer, ctypes.Array)
            or handle.keys != ["JOB_LIST"]
            or type(prepared.keepalive) is not tuple
            or len(prepared.keepalive) != 1
            or len(handle.values) != 1
            or handle.values[0] is not prepared.keepalive[0]
            or not isinstance(prepared.keepalive[0], ctypes.Array)
            or prepared.keepalive[0]._type_ is not ctypes.c_void_p
            or len(prepared.keepalive[0]) != 1
            or not _valid_value(prepared.keepalive[0][0], pointer_max)):
        raise ValueError("reviewed Buildx job attribute list required")
    return handle.buffer


def create_owned_buildx_suspended_process(api, prepared):
    """Validate an injected creation result, retaining borrowed attributes.

    The collaborator must create a suspended child with the supplied attribute
    list. Its reported predicates are not native proof of job membership.
    The caller owns the attribute list and its job handle until cleanup.
    """
    attribute_buffer = _job_attribute_buffer(prepared)
    try:
        created = api.create_suspended(attribute_buffer)
    except BaseException as error:
        raise UnknownSuspendedProcess(
            "Buildx suspended-process creation requires reconciliation") from error
    if type(created) is not SuspendedCreationResult:
        raise UnknownSuspendedProcess("Buildx creation returned noncanonical evidence")

    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (not _valid_value(created.process_handle, pointer_max)
            or not _valid_value(created.thread_handle, pointer_max)
            or created.process_handle == created.thread_handle):
        raise UnknownSuspendedProcess("Buildx creation handle ownership is unknown")

    owned = OwnedSuspendedProcess(api, created, prepared)
    valid_ids = (_valid_value(created.process_id, 0xFFFFFFFF)
                 and _valid_value(created.thread_id, 0xFFFFFFFF))
    proven_predicates = (created.suspended is True
                         and created.job_bound_at_creation is True
                         and created.appcontainer_bound_at_creation is False)
    if not valid_ids or not proven_predicates:
        owned.close()
        reason = "creation identity" if not valid_ids else "creation predicate"
        raise SuspendedProcessDenied(f"Buildx suspended-process {reason} not proven")
    return owned
