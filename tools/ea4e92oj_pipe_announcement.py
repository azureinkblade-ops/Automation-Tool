"""Inert announcement-byte validation; no filesystem or pipe authority."""

from dataclasses import dataclass
import json
import re
import uuid


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PIPE = re.compile(r"\\\\\.\\pipe\\ea4e-issuer-([0-9a-f]{32})-([0-9a-f]{32})\Z")
_FIELDS = frozenset({
    "version", "ceremony_id", "coordinator_nonce", "pipe_name",
    "creator_exe_sha256", "creator_pid", "creator_creation_time_100ns",
    "issued_unix_ms", "deadline_unix_ms",
})


class AnnouncementDenied(ValueError):
    """Announcement bytes do not match the independently pinned ceremony."""


@dataclass(frozen=True)
class ExpectedAnnouncement:
    ceremony_id: str
    coordinator_nonce: str
    creator_exe_sha256: str
    creator_pid: int
    creator_creation_time_100ns: int
    deadline_unix_ms: int


@dataclass(frozen=True)
class Announcement:
    pipe_name: str
    issued_unix_ms: int
    deadline_unix_ms: int


def _guid(value):
    if type(value) is not str:
        return False
    try:
        parsed = uuid.UUID(value)
        return value == str(parsed) and parsed.int != 0
    except (ValueError, AttributeError):
        return False


def _deny_constant(_value):
    raise AnnouncementDenied("non-finite value")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnnouncementDenied("duplicate field")
        result[key] = value
    return result


def decode_announcement(raw, *, expected, now_unix_ms):
    """Check canonical bytes only; caller must independently attest the handle."""
    if (type(raw) is not bytes or len(raw) > 1024 or not raw or
            type(expected) is not ExpectedAnnouncement or
            type(now_unix_ms) is not int or now_unix_ms <= 0 or
            not _guid(expected.ceremony_id) or
            not _guid(expected.coordinator_nonce) or
            expected.ceremony_id == expected.coordinator_nonce or
            type(expected.creator_exe_sha256) is not str or
            not _SHA256.fullmatch(expected.creator_exe_sha256) or
            type(expected.creator_pid) is not int or
            not 0 < expected.creator_pid <= 0xFFFFFFFF or
            type(expected.creator_creation_time_100ns) is not int or
            not 0 < expected.creator_creation_time_100ns <= 0xFFFFFFFFFFFFFFFF or
            type(expected.deadline_unix_ms) is not int or
            expected.deadline_unix_ms <= 0):
        raise AnnouncementDenied("invalid inputs")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_deny_constant)
    except (UnicodeError, ValueError, TypeError) as error:
        raise AnnouncementDenied("invalid JSON") from error
    if type(value) is not dict or frozenset(value) != _FIELDS:
        raise AnnouncementDenied("field set mismatch")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("ascii")
    if raw != canonical:
        raise AnnouncementDenied("noncanonical bytes")
    if (type(value["version"]) is not int or value["version"] != 1 or
            not _guid(value["ceremony_id"]) or
            not _guid(value["coordinator_nonce"]) or
            value["ceremony_id"] == value["coordinator_nonce"] or
            value["ceremony_id"] != expected.ceremony_id or
            value["coordinator_nonce"] != expected.coordinator_nonce or
            type(value["creator_exe_sha256"]) is not str or
            not _SHA256.fullmatch(value["creator_exe_sha256"]) or
            value["creator_exe_sha256"] != expected.creator_exe_sha256 or
            type(value["creator_pid"]) is not int or
            not 0 < value["creator_pid"] <= 0xFFFFFFFF or
            value["creator_pid"] != expected.creator_pid or
            type(value["creator_creation_time_100ns"]) is not int or
            not 0 < value["creator_creation_time_100ns"] <= 0xFFFFFFFFFFFFFFFF or
            value["creator_creation_time_100ns"] != expected.creator_creation_time_100ns):
        raise AnnouncementDenied("identity mismatch")
    name = value["pipe_name"]
    match = _PIPE.fullmatch(name) if type(name) is str else None
    if (match is None or match.group(1) != uuid.UUID(expected.ceremony_id).hex or
            match.group(2) == match.group(1) or
            int(match.group(2), 16) == 0):
        raise AnnouncementDenied("pipe name mismatch")
    issued = value["issued_unix_ms"]
    deadline = value["deadline_unix_ms"]
    if (type(issued) is not int or type(deadline) is not int or
            type(expected.deadline_unix_ms) is not int or
            deadline != expected.deadline_unix_ms or
            not 0 < issued <= now_unix_ms < deadline or
            deadline - issued > 120000):
        raise AnnouncementDenied("announcement expired or future dated")
    return Announcement(name, issued, deadline)
