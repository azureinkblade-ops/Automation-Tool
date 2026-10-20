"""Pure record/attestation comparison; no channel or file authority."""

from dataclasses import dataclass
import hashlib
import hmac
import re

from tools.ea4e92oj_pipe_announcement import ExpectedAnnouncement
from tools.ea4e92or_pipe_announcement_v2 import (
    ExpectedAnnouncementV2, decode_announcement_v2,
)
from tools.ea4e92ow_creator_attestation import CreatorClaims


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class BindingDenied(ValueError):
    """The claimed creator record and medium observation do not bind."""


@dataclass(frozen=True)
class MediumRecordObservation:
    volume_serial: str
    file_id: str
    exact_bytes: bytes


def bind_attestation_record(*, claims, medium, expected_announcement,
                            now_unix_ms):
    """Compare values only; caller must prove the channel and retained handle."""
    if (type(claims) is not CreatorClaims or
            type(medium) is not MediumRecordObservation or
            type(expected_announcement) is not ExpectedAnnouncement or
            type(medium.exact_bytes) is not bytes or
            not medium.exact_bytes or len(medium.exact_bytes) > 1024 or
            type(claims.record_sha256) is not str or
            _SHA256.fullmatch(claims.record_sha256) is None or
            type(medium.volume_serial) is not str or
            type(medium.file_id) is not str):
        raise BindingDenied("invalid binding inputs")
    if (medium.volume_serial != claims.record_volume_serial or
            medium.file_id != claims.record_file_id):
        raise BindingDenied("retained file identity mismatch")
    digest = hashlib.sha256(medium.exact_bytes).hexdigest()
    if not hmac.compare_digest(digest, claims.record_sha256):
        raise BindingDenied("exact record bytes mismatch")
    expected_v2 = ExpectedAnnouncementV2(
        expected_announcement, claims.record_volume_serial,
        claims.record_file_id)
    try:
        return decode_announcement_v2(medium.exact_bytes,
                                      expected=expected_v2,
                                      now_unix_ms=now_unix_ms)
    except ValueError as error:
        raise BindingDenied("v2 record denied") from error
