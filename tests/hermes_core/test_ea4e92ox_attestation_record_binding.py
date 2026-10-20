"""Pure creator claim versus medium retained-record value comparisons."""

from dataclasses import replace
import hashlib
import json

import pytest

from tools.ea4e92oj_pipe_announcement import ExpectedAnnouncement
from tools.ea4e92ow_creator_attestation import CreatorClaims
from tools.ea4e92ox_attestation_record_binding import (
    BindingDenied, MediumRecordObservation, bind_attestation_record,
)


CEREMONY = "11111111-1111-4111-8111-111111111111"
NONCE = "22222222-2222-4222-8222-222222222222"
VOLUME = "0123456789abcdef"
FILE_ID = "0123456789abcdef0123456789abcdef"
EXPECTED = ExpectedAnnouncement(CEREMONY, NONCE, "a" * 64,
                                1234, 5678, 120000)
RECORD = {
    "version": 2,
    "ceremony_id": CEREMONY,
    "coordinator_nonce": NONCE,
    "pipe_name": r"\\.\pipe\ea4e-issuer-" + CEREMONY.replace("-", "") + "-" + "3" * 32,
    "creator_exe_sha256": "a" * 64,
    "creator_pid": 1234,
    "creator_creation_time_100ns": 5678,
    "issued_unix_ms": 100000,
    "deadline_unix_ms": 120000,
    "record_volume_serial": VOLUME,
    "record_file_id": FILE_ID,
}
RAW = json.dumps(RECORD, sort_keys=True, separators=(",", ":"),
                 ensure_ascii=True).encode("ascii")
CLAIMS = CreatorClaims(VOLUME, FILE_ID, hashlib.sha256(RAW).hexdigest(),
                       "d" * 64, "e" * 64)
MEDIUM = MediumRecordObservation(VOLUME, FILE_ID, RAW)


def bind(claims=CLAIMS, medium=MEDIUM, expected=EXPECTED, now=110000):
    return bind_attestation_record(claims=claims, medium=medium,
                                   expected_announcement=expected,
                                   now_unix_ms=now)


def test_matching_values_are_only_candidate_binding():
    assert bind().pipe_name == RECORD["pipe_name"]


@pytest.mark.parametrize("medium", [
    replace(MEDIUM, volume_serial="f" * 16),
    replace(MEDIUM, file_id="f" * 32),
    replace(MEDIUM, file_id=0),
    replace(MEDIUM, exact_bytes=RAW + b" "),
    replace(MEDIUM, exact_bytes=RAW[:-1]),
    replace(MEDIUM, exact_bytes=b""),
    replace(MEDIUM, exact_bytes=RAW + b" " * 1025),
    replace(MEDIUM, exact_bytes="not bytes"),
])
def test_medium_mismatch_denies(medium):
    with pytest.raises(BindingDenied):
        bind(medium=medium)


@pytest.mark.parametrize("claims", [
    replace(CLAIMS, record_volume_serial="f" * 16),
    replace(CLAIMS, record_file_id="f" * 32),
    replace(CLAIMS, record_sha256="0" * 64),
    replace(CLAIMS, record_sha256="bad"),
    replace(CLAIMS, record_sha256=True),
])
def test_creator_claim_mismatch_denies(claims):
    with pytest.raises(BindingDenied):
        bind(claims=claims)


@pytest.mark.parametrize("expected,now", [
    (replace(EXPECTED, coordinator_nonce=CEREMONY), 110000),
    (replace(EXPECTED, creator_pid=1235), 110000),
    (EXPECTED, 120000),
    (EXPECTED, True),
])
def test_pinned_announcement_denials_propagate(expected, now):
    with pytest.raises(BindingDenied):
        bind(expected=expected, now=now)


def test_hash_match_cannot_override_malformed_v2_record():
    malformed = json.dumps(RECORD | {"version": 1}, sort_keys=True,
                           separators=(",", ":")).encode("ascii")
    claims = replace(CLAIMS, record_sha256=hashlib.sha256(malformed).hexdigest())
    with pytest.raises(BindingDenied):
        bind(claims=claims, medium=replace(MEDIUM, exact_bytes=malformed))
