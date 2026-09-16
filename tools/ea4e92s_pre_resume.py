"""Test-owned pre-resume containment verification; no native implementation."""

import ctypes
from dataclasses import dataclass

from tools.ea4e92s_profile_preflight import ProfileSnapshot
from tools.ea4e92s_profile_security_binding import BoundProfileSecurity
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess, SuspendedCreationResult)


class PreResumeDenied(RuntimeError):
    """Required containment evidence was unavailable or did not match."""


@dataclass(frozen=True)
class PreResumeEvidence:
    job_handle: int
    process_handle: int
    thread_handle: int
    process_id: int
    thread_id: int
    profile_name: str
    appcontainer_sid: bytes


def _valid_pointer(value):
    maximum = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    return type(value) is int and 0 < value <= maximum


def _validate_inputs(owned, job_handle, expected_sid):
    if type(owned) is not OwnedSuspendedProcess or owned.state != "owned":
        raise ValueError("owned suspended process required")
    creation_owner = owned.creation_owner
    security = getattr(creation_owner, "security", None)
    attributes = getattr(security, "attributes", None)
    if (type(creation_owner) is not BoundProfileSecurity
            or creation_owner.state != "owned"
            or getattr(security, "state", None) != "owned"
            or getattr(attributes, "state", None) != "owned"):
        raise ValueError("owned profile security required")
    if not _valid_pointer(job_handle):
        raise ValueError("valid job handle required")
    if type(expected_sid) is not bytes or not 8 <= len(expected_sid) <= 68:
        raise ValueError("bounded reviewed SID required")

    keepalive = getattr(attributes, "keepalive", None)
    try:
        bound_job_handle = keepalive[0][0]
    except (AttributeError, IndexError, TypeError):
        raise ValueError("creation-time job binding required") from None
    if type(bound_job_handle) is not int or bound_job_handle != job_handle:
        raise ValueError("creation-time job binding mismatch")

    profile = creation_owner.profile
    if type(profile) is not ProfileSnapshot or profile.sid != expected_sid:
        raise ValueError("independently reviewed profile SID mismatch")
    created = owned.result
    if type(created) is not SuspendedCreationResult:
        raise ValueError("canonical suspended creation result required")
    valid_result = (
        _valid_pointer(created.process_handle)
        and _valid_pointer(created.thread_handle)
        and created.process_handle != created.thread_handle
        and type(created.process_id) is int
        and 0 < created.process_id <= 0xFFFFFFFF
        and type(created.thread_id) is int
        and 0 < created.thread_id <= 0xFFFFFFFF
        and created.suspended is True
        and created.job_bound_at_creation is True
        and created.appcontainer_bound_at_creation is True)
    if not valid_result:
        raise ValueError("canonical suspended creation result required")
    return profile, created


def verify_pre_resume_containment(verifier, owned, job_handle, expected_sid):
    """Return immutable evidence only after four trusted exact-value queries.

    The injected verifier owns any resources required by its queries. This helper
    neither changes the process nor releases resources. Evidence is admission
    input for a later broker step, not proof that a native adapter is qualified.
    """
    profile, created = _validate_inputs(owned, job_handle, expected_sid)
    try:
        membership = verifier.is_process_in_job(
            created.process_handle, job_handle)
        if membership is not True:
            raise PreResumeDenied("process membership not proven")

        active_count = verifier.active_process_count(job_handle)
        if type(active_count) is not int or active_count != 1:
            raise PreResumeDenied("exact active process count not proven")

        observed_sid = verifier.process_appcontainer_sid(
            created.process_handle)
        if type(observed_sid) is not bytes or observed_sid != expected_sid:
            raise PreResumeDenied("process AppContainer SID mismatch")

        suspended = verifier.is_thread_suspended(created.thread_handle)
        if suspended is not True:
            raise PreResumeDenied("primary thread suspended state not proven")
    except PreResumeDenied:
        raise
    except BaseException as error:
        raise PreResumeDenied("pre-resume containment query failed") from error

    return PreResumeEvidence(
        job_handle, created.process_handle, created.thread_handle,
        created.process_id, created.thread_id, profile.profile_name,
        observed_sid)
