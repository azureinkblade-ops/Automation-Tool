"""Fake-only v2 ceremony composition; no native or durable authority."""

from tools.ea4e92oj_pipe_announcement import ExpectedAnnouncement
from tools.ea4e92ow_creator_attestation import (
    ExpectedCreatorAttestation, decode_creator_attestation,
)
from tools.ea4e92ox_attestation_record_binding import (
    MediumRecordObservation, bind_attestation_record,
)


class FakeCeremonyDenied(ValueError):
    """The inert ceremony did not satisfy its pinned value contract."""


class InertV2Ceremony:
    """One attempt in one process lifetime; never grants native use."""

    def __init__(self, announcement_expected, attestation_expected, *, fake_only):
        if (fake_only is not True or
                type(announcement_expected) is not ExpectedAnnouncement or
                type(attestation_expected) is not ExpectedCreatorAttestation or
                announcement_expected.ceremony_id != attestation_expected.ceremony_id or
                announcement_expected.coordinator_nonce !=
                attestation_expected.coordinator_nonce or
                announcement_expected.creator_pid != attestation_expected.creator_pid or
                announcement_expected.creator_creation_time_100ns !=
                attestation_expected.creator_creation_time_100ns or
                announcement_expected.creator_exe_sha256 !=
                attestation_expected.creator_exe_sha256 or
                announcement_expected.deadline_unix_ms !=
                attestation_expected.deadline_unix_ms):
            raise FakeCeremonyDenied("invalid fake-only pinned expectations")
        self._announcement_expected = announcement_expected
        self._attestation_expected = attestation_expected
        self.state = "NEW"

    def consume(self, attestation_bytes, medium_record, *, now_unix_ms):
        if self.state != "NEW":
            raise FakeCeremonyDenied("attempt already consumed")
        self.state = "UNKNOWN"
        if type(medium_record) is not MediumRecordObservation:
            raise FakeCeremonyDenied("invalid medium observation")
        try:
            claims = decode_creator_attestation(
                attestation_bytes, expected=self._attestation_expected,
                now_unix_ms=now_unix_ms)
            result = bind_attestation_record(
                claims=claims, medium=medium_record,
                expected_announcement=self._announcement_expected,
                now_unix_ms=now_unix_ms)
        except ValueError as error:
            raise FakeCeremonyDenied("inert ceremony denied") from error
        self.state = "CONSUMED"
        return result

    def close(self):
        if self.state == "CLOSED":
            raise FakeCeremonyDenied("already closed")
        self.state = "CLOSED"
