"""Inert v2 announcement-byte denial matrix."""

from dataclasses import replace
import json

import pytest

from tools.ea4e92oj_pipe_announcement import AnnouncementDenied, ExpectedAnnouncement
from tools.ea4e92or_pipe_announcement_v2 import (
    ExpectedAnnouncementV2, decode_announcement_v2,
)


CEREMONY = "11111111-1111-4111-8111-111111111111"
NONCE = "22222222-2222-4222-8222-222222222222"
VOLUME = "0123456789abcdef"
FILE_ID = "0123456789abcdef0123456789abcdef"
BASE = ExpectedAnnouncement(CEREMONY, NONCE, "a" * 64, 1234, 5678, 120000)
EXPECTED = ExpectedAnnouncementV2(BASE, VOLUME, FILE_ID)
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


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def test_exact_inert_v2_record():
    result = decode_announcement_v2(encoded(RECORD), expected=EXPECTED,
                                    now_unix_ms=110000)
    assert result.pipe_name == RECORD["pipe_name"]
    assert result.record_volume_serial == VOLUME
    assert result.record_file_id == FILE_ID


@pytest.mark.parametrize("change", [
    {"version": 1}, {"version": True},
    {"record_volume_serial": "0" * 16},
    {"record_volume_serial": "A" + VOLUME[1:]},
    {"record_volume_serial": VOLUME[:-1]},
    {"record_volume_serial": True},
    {"record_file_id": "0" * 32},
    {"record_file_id": "A" + FILE_ID[1:]},
    {"record_file_id": FILE_ID[:-1]},
    {"record_file_id": FILE_ID + "0"},
    {"record_file_id": None},
    {"coordinator_nonce": CEREMONY},
    {"creator_pid": 1235},
    {"deadline_unix_ms": 120001},
])
def test_record_mutations_deny(change):
    with pytest.raises(AnnouncementDenied):
        decode_announcement_v2(encoded(RECORD | change), expected=EXPECTED,
                               now_unix_ms=110000)


@pytest.mark.parametrize("raw", [
    b"", b"{}", b"[]", b"{", b"\xff", b" " + encoded(RECORD),
    encoded(RECORD) + b"\n", encoded(RECORD) + b" " * 1025,
    encoded(RECORD).replace(b'"version":2', b'"version":2,"version":2'),
    encoded(RECORD | {"extra": 1}),
    encoded({key: value for key, value in RECORD.items()
             if key != "record_file_id"}),
])
def test_malformed_v2_denies(raw):
    with pytest.raises(AnnouncementDenied):
        decode_announcement_v2(raw, expected=EXPECTED, now_unix_ms=110000)


@pytest.mark.parametrize("expected", [
    replace(EXPECTED, creator_volume_serial="f" * 16),
    replace(EXPECTED, creator_file_id="f" * 32),
    replace(EXPECTED, creator_file_id="0" * 32),
    replace(EXPECTED, creator_volume_serial="bad"),
    replace(EXPECTED, base=replace(BASE, coordinator_nonce=CEREMONY)),
])
def test_independent_expectation_mismatch_denies(expected):
    with pytest.raises(AnnouncementDenied):
        decode_announcement_v2(encoded(RECORD), expected=expected,
                               now_unix_ms=110000)


@pytest.mark.parametrize("now", [99999, 120000, True, "110000"])
def test_time_boundary_denies(now):
    with pytest.raises(AnnouncementDenied):
        decode_announcement_v2(encoded(RECORD), expected=EXPECTED,
                               now_unix_ms=now)
