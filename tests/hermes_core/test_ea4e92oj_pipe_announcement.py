"""Pure announcement-byte checks; no file, process, or pipe is opened."""

from dataclasses import replace
import json

import pytest

from tools.ea4e92oj_pipe_announcement import (
    AnnouncementDenied, ExpectedAnnouncement, decode_announcement,
)


CEREMONY = "11111111-1111-4111-8111-111111111111"
NONCE = "22222222-2222-4222-8222-222222222222"
EXPECTED = ExpectedAnnouncement(CEREMONY, NONCE, "a" * 64, 1234, 5678, 120000)
RECORD = {
    "version": 1,
    "ceremony_id": CEREMONY,
    "coordinator_nonce": NONCE,
    "pipe_name": r"\\.\pipe\ea4e-issuer-" + CEREMONY.replace("-", "") + "-" + "3" * 32,
    "creator_exe_sha256": "a" * 64,
    "creator_pid": 1234,
    "creator_creation_time_100ns": 5678,
    "issued_unix_ms": 100000,
    "deadline_unix_ms": 120000,
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def test_exact_inert_record():
    result = decode_announcement(encoded(RECORD), expected=EXPECTED,
                                 now_unix_ms=110000)
    assert result.pipe_name == RECORD["pipe_name"]
    assert result.issued_unix_ms == 100000


@pytest.mark.parametrize("change", [
    {"version": 2}, {"version": True},
    {"ceremony_id": NONCE}, {"coordinator_nonce": CEREMONY},
    {"coordinator_nonce": "0" * 36},
    {"pipe_name": r"\\.\pipe\ea4e-issuer-" + "4" * 32 + "-" + "3" * 32},
    {"pipe_name": r"\\.\pipe\ea4e-issuer-" + "1" * 32 + "-" + "0" * 32},
    {"pipe_name": "other"},
    {"creator_exe_sha256": "b" * 64},
    {"creator_pid": 1235}, {"creator_pid": True},
    {"creator_creation_time_100ns": 5679},
    {"issued_unix_ms": 110001}, {"issued_unix_ms": 0},
    {"deadline_unix_ms": 120001}, {"deadline_unix_ms": True},
])
def test_record_mutations_deny(change):
    with pytest.raises(AnnouncementDenied):
        decode_announcement(encoded(RECORD | change), expected=EXPECTED,
                            now_unix_ms=110000)


@pytest.mark.parametrize("raw", [
    b"", b"{}", b"[]", b"{", b"\xff", b"\xef\xbb\xbf" + encoded(RECORD),
    b" " + encoded(RECORD), encoded(RECORD) + b"\n",
    encoded(RECORD) + b" " * 1025,
    encoded(RECORD).replace(b'"version":1', b'"version":1,"version":1'),
    encoded(RECORD).replace(b'"version":1', b'"version":NaN'),
    encoded(RECORD | {"extra": 1}),
    encoded({key: value for key, value in RECORD.items() if key != "version"}),
])
def test_malformed_or_noncanonical_bytes_deny(raw):
    with pytest.raises(AnnouncementDenied):
        decode_announcement(raw, expected=EXPECTED, now_unix_ms=110000)


@pytest.mark.parametrize("now", [99999, 120000, True, "110000"])
def test_time_boundary_deny(now):
    with pytest.raises(AnnouncementDenied):
        decode_announcement(encoded(RECORD), expected=EXPECTED,
                            now_unix_ms=now)


def test_replay_against_different_expected_nonce_denies():
    with pytest.raises(AnnouncementDenied):
        decode_announcement(encoded(RECORD),
                            expected=replace(EXPECTED,
                                             coordinator_nonce="44444444-4444-4444-8444-444444444444"),
                            now_unix_ms=110000)


@pytest.mark.parametrize("change", [
    {"ceremony_id": "broken"}, {"coordinator_nonce": CEREMONY},
    {"creator_exe_sha256": "bad"}, {"creator_pid": True},
    {"creator_creation_time_100ns": -1}, {"deadline_unix_ms": "120000"},
])
def test_malformed_independent_expectation_denies(change):
    with pytest.raises(AnnouncementDenied):
        decode_announcement(encoded(RECORD), expected=replace(EXPECTED, **change),
                            now_unix_ms=110000)


def test_record_cannot_extend_lease():
    later = RECORD | {"deadline_unix_ms": 240001, "issued_unix_ms": 100000}
    with pytest.raises(AnnouncementDenied):
        decode_announcement(encoded(later),
                            expected=replace(EXPECTED, deadline_unix_ms=240001),
                            now_unix_ms=110000)
