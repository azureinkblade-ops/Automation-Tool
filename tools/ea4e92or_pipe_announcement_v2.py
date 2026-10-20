"""Inert v2 announcement syntax checks; inputs do not confer authority."""

from dataclasses import dataclass
import json
import re

from tools.ea4e92oj_pipe_announcement import (
    AnnouncementDenied,
    ExpectedAnnouncement,
    _deny_constant,
    _unique_object,
    decode_announcement,
)


_V1_FIELDS = frozenset({
    "version", "ceremony_id", "coordinator_nonce", "pipe_name",
    "creator_exe_sha256", "creator_pid", "creator_creation_time_100ns",
    "issued_unix_ms", "deadline_unix_ms",
})
_V2_FIELDS = _V1_FIELDS | {"record_volume_serial", "record_file_id"}
_VOLUME = re.compile(r"[0-9a-f]{16}\Z")
_FILE_ID = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class ExpectedAnnouncementV2:
    base: ExpectedAnnouncement
    creator_volume_serial: str
    creator_file_id: str


@dataclass(frozen=True)
class AnnouncementV2:
    pipe_name: str
    issued_unix_ms: int
    deadline_unix_ms: int
    record_volume_serial: str
    record_file_id: str


def _valid_identity(volume, file_id):
    return (type(volume) is str and _VOLUME.fullmatch(volume) is not None and
            int(volume, 16) != 0 and type(file_id) is str and
            _FILE_ID.fullmatch(file_id) is not None and int(file_id, 16) != 0)


def decode_announcement_v2(raw, *, expected, now_unix_ms):
    """Validate bytes against independently obtained expectations only.

    The caller must authenticate the creator attestation and compare both
    retained file handles; this parser performs neither operation.
    """
    if (type(raw) is not bytes or not raw or len(raw) > 1024 or
            type(expected) is not ExpectedAnnouncementV2 or
            not _valid_identity(expected.creator_volume_serial,
                                expected.creator_file_id)):
        raise AnnouncementDenied("invalid v2 inputs")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_deny_constant)
    except (UnicodeError, ValueError, TypeError) as error:
        raise AnnouncementDenied("invalid v2 JSON") from error
    if type(value) is not dict or frozenset(value) != _V2_FIELDS:
        raise AnnouncementDenied("v2 field set mismatch")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("ascii")
    if raw != canonical or type(value["version"]) is not int or value["version"] != 2:
        raise AnnouncementDenied("noncanonical or wrong v2 version")
    volume = value["record_volume_serial"]
    file_id = value["record_file_id"]
    if (not _valid_identity(volume, file_id) or
            volume != expected.creator_volume_serial or
            file_id != expected.creator_file_id):
        raise AnnouncementDenied("record identity mismatch")
    v1 = {key: value[key] for key in _V1_FIELDS}
    v1["version"] = 1
    v1_bytes = json.dumps(v1, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii")
    common = decode_announcement(v1_bytes, expected=expected.base,
                                 now_unix_ms=now_unix_ms)
    return AnnouncementV2(common.pipe_name, common.issued_unix_ms,
                          common.deadline_unix_ms, volume, file_id)
