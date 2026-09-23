"""Fake-only pre-resume observations; creator provenance remains untrusted."""

from dataclasses import dataclass

from tools.ea4e92s_creation_provenance import validate_creation_receipt
from tools.ea4e92s_pre_resume import _validate_inputs


class ProvenanceObservationDenied(RuntimeError):
    """An exact pre-resume observation could not be established."""


@dataclass(frozen=True)
class UntrustedCreationObservation:
    receipt: object
    profile_name: str
    appcontainer_sid: bytes


def observe_fake_pre_resume(
        verifier, receipt, owned, *, request_id, adapter_sha256,
        job_handle, expected_sid):
    """Check three independent values, without granting resume authority.

    The receipt is caller-constructed until a reviewed native creator owns it.
    Even a successful result is not a trusted pre-resume verdict.
    """
    try:
        validate_creation_receipt(
            receipt, owned, request_id=request_id,
            adapter_sha256=adapter_sha256, job_handle=job_handle)
        profile, created = _validate_inputs(owned, job_handle, expected_sid)
    except (ValueError, AttributeError, TypeError) as error:
        raise ProvenanceObservationDenied("creation inputs not proven") from error

    try:
        if verifier.is_process_in_job(
                created.process_handle, job_handle) is not True:
            raise ProvenanceObservationDenied("process membership not proven")
        count = verifier.active_process_count(job_handle)
        if type(count) is not int or count != 1:
            raise ProvenanceObservationDenied("exact active count not proven")
        sid = verifier.process_appcontainer_sid(created.process_handle)
        if type(sid) is not bytes or sid != expected_sid:
            raise ProvenanceObservationDenied("AppContainer SID mismatch")
    except ProvenanceObservationDenied:
        raise
    except Exception as error:
        raise ProvenanceObservationDenied("containment query failed") from error

    return UntrustedCreationObservation(receipt, profile.profile_name, sid)
