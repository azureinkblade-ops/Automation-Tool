"""Pure challenge-frame contract tests; no pipe or agent is invoked."""

from dataclasses import replace
import json

import pytest

from tools.ea4e92ne_app_challenge_frame import (
    AppChallengeExpectation,
    AppChallengeFrameDenied,
    MAX_FRAME_BYTES,
    encode_app_challenge_frame,
    parse_app_challenge_frame,
)


EXPECTED = AppChallengeExpectation(
    "718d4e99-9d30-42d1-a2ed-c3bf55734ac2",
    "621e57b3-ef5c-4fbe-8d0a-81f78d2c4ba3",
    "84bb0bea-ed17-4a29-a9ef-c2f76c8d16eb",
)


def test_canonical_frame_matches_only_expected_fields():
    frame = encode_app_challenge_frame(EXPECTED)
    parsed = parse_app_challenge_frame(frame, EXPECTED)
    assert parsed.ceremony_id == EXPECTED.ceremony_id
    assert parsed.challenge_id == EXPECTED.challenge_id
    assert parsed.app_instance_nonce == EXPECTED.app_instance_nonce
    assert len(parsed.frame_sha256) == 64
    assert frame == encode_app_challenge_frame(EXPECTED)


@pytest.mark.parametrize("changed", [
    replace(EXPECTED, ceremony_id="0" * 8 + EXPECTED.ceremony_id[8:]),
    replace(EXPECTED, challenge_id="0" * 8 + EXPECTED.challenge_id[8:]),
    replace(EXPECTED, app_instance_nonce="0" * 8 + EXPECTED.app_instance_nonce[8:]),
])
def test_wrong_expected_identity_denies(changed):
    with pytest.raises(AppChallengeFrameDenied, match="mismatch"):
        parse_app_challenge_frame(encode_app_challenge_frame(EXPECTED), changed)


@pytest.mark.parametrize("bad", [
    None, b"", b"x" * (MAX_FRAME_BYTES + 1),
    b"\xff", b"{}", b"[]", b"null",
    b'{"ceremony_id":1}',
])
def test_malformed_or_unbounded_frame_denies(bad):
    with pytest.raises(AppChallengeFrameDenied):
        parse_app_challenge_frame(bad, EXPECTED)


@pytest.mark.parametrize("changed", [
    {"schema_version": "wrong"},
    {"verified": True},
    {"app_instance_nonce": "not-a-nonce"},
])
def test_wrong_schema_extra_field_or_nonce_denies(changed):
    payload = json.loads(encode_app_challenge_frame(EXPECTED))
    payload.update(changed)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(AppChallengeFrameDenied):
        parse_app_challenge_frame(raw, EXPECTED)


def test_duplicate_key_or_noncanonical_bytes_denies():
    frame = encode_app_challenge_frame(EXPECTED)
    duplicate = frame[:-1] + b',"ceremony_id":"' + EXPECTED.ceremony_id.encode() + b'"}'
    for raw in (duplicate, b" " + frame, frame + b"\n"):
        with pytest.raises(AppChallengeFrameDenied):
            parse_app_challenge_frame(raw, EXPECTED)


@pytest.mark.parametrize("bad", [
    replace(EXPECTED, challenge_id=EXPECTED.ceremony_id),
    replace(EXPECTED, ceremony_id="BAD"),
    replace(EXPECTED, app_instance_nonce=EXPECTED.app_instance_nonce.upper()),
    None,
])
def test_invalid_expectation_denies_before_encoding_or_parsing(bad):
    with pytest.raises(AppChallengeFrameDenied):
        encode_app_challenge_frame(bad)
    with pytest.raises(AppChallengeFrameDenied):
        parse_app_challenge_frame(encode_app_challenge_frame(EXPECTED), bad)
