"""Value-only receipt tests; no native launch, resume or resource operation."""

from dataclasses import replace
from types import SimpleNamespace
import inspect

import pytest

from tools import ea4e92s_creation_provenance as subject
from tools.ea4e92s_suspended_process import (
    OwnedSuspendedProcess,
    SuspendedCreationResult,
)


REQUEST = "request-0001"
ADAPTER = "a" * 64
JOB, PROCESS, THREAD = 11, 22, 33
PID, TID = 201, 202
FLAGS = subject.CREATE_SUSPENDED | subject.EXTENDED_STARTUPINFO_PRESENT


def setup():
    attributes = SimpleNamespace(state="owned", keepalive=[[JOB]])
    security = SimpleNamespace(state="owned", attributes=attributes)
    owner = SimpleNamespace(state="owned", security=security)
    result = SuspendedCreationResult(
        PROCESS, THREAD, PID, TID, True, True, True)
    owned = OwnedSuspendedProcess(object(), result, owner)
    receipt = subject.SuspendedCreationReceipt(
        REQUEST, ADAPTER, FLAGS, owned, owner, JOB,
        PROCESS, THREAD, PID, TID)
    return receipt, owned


def verify(receipt, owned, **changes):
    expected = dict(request_id=REQUEST, adapter_sha256=ADAPTER,
                    job_handle=JOB)
    expected.update(changes)
    return subject.validate_creation_receipt(receipt, owned, **expected)


def test_exact_receipt_returns_same_in_memory_value_without_calls():
    receipt, owned = setup()
    assert verify(receipt, owned) is receipt
    assert receipt.creation_owner is owned.creation_owner


@pytest.mark.parametrize("flags", [
    0, subject.CREATE_SUSPENDED,
    subject.EXTENDED_STARTUPINFO_PRESENT, -1, True, "0x80004",
    0x1_0008_0004, FLAGS | 0x10,
])
def test_missing_or_malformed_creation_flags_denied(flags):
    receipt, owned = setup()
    with pytest.raises(subject.CreationProvenanceDenied, match="flags"):
        verify(replace(receipt, creation_flags=flags), owned)


@pytest.mark.parametrize("change", [
    {"job_handle": 0}, {"job_handle": PROCESS},
    {"process_handle": THREAD}, {"thread_handle": 0},
    {"process_id": TID}, {"thread_id": 0},
])
def test_swapped_or_invalid_resource_identity_denied(change):
    receipt, owned = setup()
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(replace(receipt, **change), owned)


def test_cross_request_adapter_and_owner_replay_denied():
    receipt, owned = setup()
    other_receipt, other_owned = setup()
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, owned, request_id="another-request")
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, owned, adapter_sha256="b" * 64)
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, other_owned)
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(replace(other_receipt, owned=owned), owned)


@pytest.mark.parametrize("field", [
    "suspended", "job_bound_at_creation", "appcontainer_bound_at_creation",
])
def test_creator_predicate_drift_denied(field):
    receipt, owned = setup()
    owned.result = replace(owned.result, **{field: False})
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, owned)


def test_closed_owner_and_attribute_drift_denied():
    receipt, owned = setup()
    owned.state = "closed"
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, owned)
    owned.state = "owned"
    owned.creation_owner.security.attributes.keepalive[0][0] = 99
    with pytest.raises(subject.CreationProvenanceDenied):
        verify(receipt, owned)


def test_receipt_does_not_itself_prove_native_execution():
    source = inspect.getsource(subject)
    for forbidden in (
            "WinDLL", "CreateProcessW", "ResumeThread", "SuspendThread",
            "subprocess", "OpenProcess", "OpenThread"):
        assert forbidden not in source
