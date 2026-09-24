"""Value-only creation receipt for a future reviewed suspended launcher."""

import ctypes
from dataclasses import dataclass
import re

from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess,
    SuspendedCreationResult,
)


CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CreationProvenanceDenied(ValueError):
    """Creation provenance is absent, conflicted or not yet trustworthy."""


@dataclass(frozen=True)
class SuspendedCreationReceipt:
    request_id: str
    adapter_sha256: str
    creation_flags: int
    owned: OwnedSuspendedProcess
    creation_owner: object
    job_handle: int
    process_handle: int
    thread_handle: int
    process_id: int
    thread_id: int


def _positive(value, maximum):
    return type(value) is int and 0 < value <= maximum


def validate_creation_receipt(
        receipt, owned, *, request_id, adapter_sha256, job_handle):
    """Validate exact in-memory linkage, not the truth of a native API call."""
    pointer_max = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if (type(receipt) is not SuspendedCreationReceipt
            or type(owned) is not OwnedSuspendedProcess
            or owned.state != "owned" or receipt.owned is not owned
            or receipt.creation_owner is not owned.creation_owner):
        raise CreationProvenanceDenied("exact owned creation receipt required")
    if (type(request_id) is not str or not request_id or "\0" in request_id
            or receipt.request_id != request_id):
        raise CreationProvenanceDenied("request identity conflicts")
    if (type(adapter_sha256) is not str
            or _SHA256.fullmatch(adapter_sha256) is None
            or receipt.adapter_sha256 != adapter_sha256):
        raise CreationProvenanceDenied("adapter identity conflicts")
    flags = receipt.creation_flags
    required = (CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
                | EXTENDED_STARTUPINFO_PRESENT)
    if type(flags) is not int or flags != required:
        raise CreationProvenanceDenied("suspended creation flags unavailable")

    result = owned.result
    if type(result) is not SuspendedCreationResult:
        raise CreationProvenanceDenied("canonical creation result required")
    handles = (receipt.job_handle, receipt.process_handle,
               receipt.thread_handle)
    if (not _positive(job_handle, pointer_max)
            or receipt.job_handle != job_handle
            or any(not _positive(value, pointer_max) for value in handles)
            or len(set(handles)) != 3
            or (receipt.process_handle, receipt.thread_handle)
            != (result.process_handle, result.thread_handle)
            or not _positive(receipt.process_id, 0xFFFFFFFF)
            or not _positive(receipt.thread_id, 0xFFFFFFFF)
            or (receipt.process_id, receipt.thread_id)
            != (result.process_id, result.thread_id)
            or result.suspended is not True
            or result.job_bound_at_creation is not True
            or result.appcontainer_bound_at_creation is not True):
        raise CreationProvenanceDenied("creation resource identity conflicts")

    security = getattr(receipt.creation_owner, "security", None)
    attributes = getattr(security, "attributes", None)
    if (getattr(receipt.creation_owner, "state", None) != "owned"
            or getattr(security, "state", None) != "owned"
            or getattr(attributes, "state", None) != "owned"):
        raise CreationProvenanceDenied("creation attributes no longer owned")
    try:
        bound_job = attributes.keepalive[0][0]
    except (AttributeError, IndexError, TypeError) as error:
        raise CreationProvenanceDenied("creation-time job binding unavailable") from error
    if type(bound_job) is not int or bound_job != job_handle:
        raise CreationProvenanceDenied("creation-time job binding conflicts")
    return receipt
