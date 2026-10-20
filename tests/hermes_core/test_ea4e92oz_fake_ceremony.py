"""Fake-only v2 composition and one-process attempt accounting."""

from dataclasses import replace
import hashlib
import json

import pytest

from tools.ea4e92oz_fake_ceremony import FakeCeremonyDenied, InertV2Ceremony
from tests.hermes_core import test_ea4e92ow_creator_attestation as attestation
from tests.hermes_core import test_ea4e92ox_attestation_record_binding as record


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


ATTESTATION = encoded(attestation.RECORD | {
    "record_sha256": hashlib.sha256(record.RAW).hexdigest(),
})


def ceremony():
    return InertV2Ceremony(record.EXPECTED, attestation.EXPECTED,
                           fake_only=True)


def test_fake_end_to_end_value_composition_and_replay_denial():
    attempt = ceremony()
    result = attempt.consume(ATTESTATION, record.MEDIUM, now_unix_ms=110000)
    assert result.pipe_name == record.RECORD["pipe_name"]
    assert attempt.state == "CONSUMED"
    with pytest.raises(FakeCeremonyDenied, match="already consumed"):
        attempt.consume(ATTESTATION, record.MEDIUM, now_unix_ms=110001)
    attempt.close()
    assert attempt.state == "CLOSED"


@pytest.mark.parametrize("changed_attestation,changed_medium", [
    (b"{}", record.MEDIUM),
    (ATTESTATION + b"\n", record.MEDIUM),
    (encoded(attestation.RECORD | {
        "record_sha256": "0" * 64,
    }), record.MEDIUM),
    (ATTESTATION, replace(record.MEDIUM, file_id="f" * 32)),
    (ATTESTATION, replace(record.MEDIUM, exact_bytes=record.RAW + b" ")),
    (ATTESTATION, None),
])
def test_failed_first_attempt_is_poisoned(changed_attestation,
                                          changed_medium):
    attempt = ceremony()
    with pytest.raises(FakeCeremonyDenied):
        attempt.consume(changed_attestation, changed_medium,
                        now_unix_ms=110000)
    assert attempt.state == "UNKNOWN"
    with pytest.raises(FakeCeremonyDenied, match="already consumed"):
        attempt.consume(ATTESTATION, record.MEDIUM, now_unix_ms=110000)


@pytest.mark.parametrize("fake_only", [False, None, 1, "true"])
def test_no_native_mode(fake_only):
    with pytest.raises(FakeCeremonyDenied):
        InertV2Ceremony(record.EXPECTED, attestation.EXPECTED,
                        fake_only=fake_only)


def test_pinned_expectations_must_agree_before_first_attempt():
    with pytest.raises(FakeCeremonyDenied):
        InertV2Ceremony(replace(record.EXPECTED, creator_pid=1235),
                        attestation.EXPECTED, fake_only=True)


def test_closed_attempt_denies_and_close_is_one_shot():
    attempt = ceremony()
    attempt.close()
    with pytest.raises(FakeCeremonyDenied, match="already consumed"):
        attempt.consume(ATTESTATION, record.MEDIUM, now_unix_ms=110000)
    with pytest.raises(FakeCeremonyDenied, match="already closed"):
        attempt.close()
