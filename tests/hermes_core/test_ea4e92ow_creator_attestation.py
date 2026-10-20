"""Pure attestation syntax and pinned-identity denial matrix."""

from dataclasses import replace
import json

import pytest

from tools.ea4e92ow_creator_attestation import (
    AttestationDenied, ExpectedCreatorAttestation, decode_creator_attestation,
)


CEREMONY = "11111111-1111-4111-8111-111111111111"
NONCE = "22222222-2222-4222-8222-222222222222"
EXPECTED = ExpectedCreatorAttestation(CEREMONY, NONCE, 1234, 5678,
                                      "a" * 64, "b" * 64, 120000)
RECORD = {
    "version": 1,
    "ceremony_id": CEREMONY,
    "coordinator_nonce": NONCE,
    "creator_pid": 1234,
    "creator_creation_time_100ns": 5678,
    "creator_exe_sha256": "a" * 64,
    "installer_manifest_sha256": "b" * 64,
    "record_volume_serial": "0123456789abcdef",
    "record_file_id": "0123456789abcdef0123456789abcdef",
    "record_sha256": "c" * 64,
    "record_descriptor_sha256": "d" * 64,
    "pipe_descriptor_sha256": "e" * 64,
    "issued_unix_ms": 100000,
    "deadline_unix_ms": 120000,
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def test_canonical_claims_are_not_authority():
    claims = decode_creator_attestation(encoded(RECORD), expected=EXPECTED,
                                        now_unix_ms=110000)
    assert claims.record_volume_serial == RECORD["record_volume_serial"]
    assert claims.record_file_id == RECORD["record_file_id"]
    assert claims.record_sha256 == "c" * 64


@pytest.mark.parametrize("change", [
    {"version": 2}, {"version": True},
    {"ceremony_id": NONCE}, {"coordinator_nonce": CEREMONY},
    {"creator_pid": 1235}, {"creator_pid": True},
    {"creator_creation_time_100ns": 5679},
    {"creator_exe_sha256": "f" * 64},
    {"installer_manifest_sha256": "f" * 64},
    {"record_volume_serial": "0" * 16},
    {"record_volume_serial": "A" + RECORD["record_volume_serial"][1:]},
    {"record_file_id": "0" * 32},
    {"record_file_id": "bad"},
    {"record_sha256": "C" * 64},
    {"record_descriptor_sha256": "bad"},
    {"pipe_descriptor_sha256": None},
    {"issued_unix_ms": 110001},
    {"deadline_unix_ms": 120001},
])
def test_record_mutations_deny(change):
    with pytest.raises(AttestationDenied):
        decode_creator_attestation(encoded(RECORD | change), expected=EXPECTED,
                                   now_unix_ms=110000)


@pytest.mark.parametrize("raw", [
    b"", b"{}", b"[]", b"{", b"\xff", b" " + encoded(RECORD),
    encoded(RECORD) + b"\n", encoded(RECORD) + b" " * 1025,
    encoded(RECORD).replace(b'"version":1', b'"version":1,"version":1'),
    encoded(RECORD).replace(b'"version":1', b'"version":NaN'),
    encoded(RECORD | {"extra": 1}),
    encoded({key: value for key, value in RECORD.items()
             if key != "record_sha256"}),
])
def test_malformed_or_noncanonical_denies(raw):
    with pytest.raises(AttestationDenied):
        decode_creator_attestation(raw, expected=EXPECTED, now_unix_ms=110000)


@pytest.mark.parametrize("change", [
    {"coordinator_nonce": CEREMONY},
    {"creator_pid": True},
    {"creator_exe_sha256": "bad"},
    {"installer_manifest_sha256": "bad"},
    {"deadline_unix_ms": True},
])
def test_invalid_expectation_denies(change):
    with pytest.raises(AttestationDenied):
        decode_creator_attestation(encoded(RECORD),
                                   expected=replace(EXPECTED, **change),
                                   now_unix_ms=110000)


@pytest.mark.parametrize("now", [99999, 120000, True, "110000"])
def test_time_boundary_denies(now):
    with pytest.raises(AttestationDenied):
        decode_creator_attestation(encoded(RECORD), expected=EXPECTED,
                                   now_unix_ms=now)
