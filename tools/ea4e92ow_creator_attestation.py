"""Inert creator-attestation byte checks; channel authentication is external."""

from dataclasses import dataclass
import json
import re

from tools.ea4e92oj_pipe_announcement import (
    AnnouncementDenied,
    _deny_constant,
    _guid,
    _unique_object,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_VOLUME = re.compile(r"[0-9a-f]{16}\Z")
_FILE_ID = re.compile(r"[0-9a-f]{32}\Z")
_FIELDS = frozenset({
    "version", "ceremony_id", "coordinator_nonce", "creator_pid",
    "creator_creation_time_100ns", "creator_exe_sha256",
    "installer_manifest_sha256", "record_volume_serial", "record_file_id",
    "record_sha256", "record_descriptor_sha256", "pipe_descriptor_sha256",
    "issued_unix_ms", "deadline_unix_ms",
})


class AttestationDenied(ValueError):
    """Attestation syntax or independently pinned identity did not match."""


@dataclass(frozen=True)
class ExpectedCreatorAttestation:
    ceremony_id: str
    coordinator_nonce: str
    creator_pid: int
    creator_creation_time_100ns: int
    creator_exe_sha256: str
    installer_manifest_sha256: str
    deadline_unix_ms: int


@dataclass(frozen=True)
class CreatorClaims:
    record_volume_serial: str
    record_file_id: str
    record_sha256: str
    record_descriptor_sha256: str
    pipe_descriptor_sha256: str


def _hex(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def decode_creator_attestation(raw, *, expected, now_unix_ms):
    """Parse exact bytes; caller must authenticate the channel and handles."""
    if (type(raw) is not bytes or not raw or len(raw) > 1024 or
            type(expected) is not ExpectedCreatorAttestation or
            type(now_unix_ms) is not int or now_unix_ms <= 0 or
            not _guid(expected.ceremony_id) or
            not _guid(expected.coordinator_nonce) or
            expected.ceremony_id == expected.coordinator_nonce or
            type(expected.creator_pid) is not int or
            not 0 < expected.creator_pid <= 0xFFFFFFFF or
            type(expected.creator_creation_time_100ns) is not int or
            not 0 < expected.creator_creation_time_100ns <= 0xFFFFFFFFFFFFFFFF or
            not _hex(expected.creator_exe_sha256, _SHA256) or
            not _hex(expected.installer_manifest_sha256, _SHA256) or
            type(expected.deadline_unix_ms) is not int or
            expected.deadline_unix_ms <= 0):
        raise AttestationDenied("invalid independent expectation")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_deny_constant)
    except (UnicodeError, ValueError, TypeError, AnnouncementDenied) as error:
        raise AttestationDenied("invalid attestation JSON") from error
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise AttestationDenied("field set mismatch")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("ascii")
    if raw != canonical or type(value["version"]) is not int or value["version"] != 1:
        raise AttestationDenied("noncanonical or wrong version")
    for key in ("ceremony_id", "coordinator_nonce", "creator_pid",
                "creator_creation_time_100ns", "creator_exe_sha256",
                "installer_manifest_sha256", "deadline_unix_ms"):
        if type(value[key]) is not type(getattr(expected, key)) or \
                value[key] != getattr(expected, key):
            raise AttestationDenied("pinned identity mismatch")
    volume = value["record_volume_serial"]
    file_id = value["record_file_id"]
    if (not _hex(volume, _VOLUME) or int(volume, 16) == 0 or
            not _hex(file_id, _FILE_ID) or int(file_id, 16) == 0):
        raise AttestationDenied("record identity shape")
    for key in ("record_sha256", "record_descriptor_sha256",
                "pipe_descriptor_sha256"):
        if not _hex(value[key], _SHA256):
            raise AttestationDenied("digest shape")
    issued = value["issued_unix_ms"]
    deadline = value["deadline_unix_ms"]
    if (type(issued) is not int or type(deadline) is not int or
            not 0 < issued <= now_unix_ms < deadline or
            deadline - issued > 120000):
        raise AttestationDenied("expired or future attestation")
    return CreatorClaims(volume, file_id, value["record_sha256"],
                         value["record_descriptor_sha256"],
                         value["pipe_descriptor_sha256"])
