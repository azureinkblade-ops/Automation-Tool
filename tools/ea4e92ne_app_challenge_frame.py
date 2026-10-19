"""Value-only app challenge frame; transport and client identity are external."""

from dataclasses import dataclass
import hashlib
import json
import uuid

from tools.hermes_core.hashing import canonical_json


SCHEMA_VERSION = "ea4e92ne-app-challenge-v1"
MAX_FRAME_BYTES = 512
_FIELDS = frozenset({
    "schema_version", "ceremony_id", "challenge_id", "app_instance_nonce",
})


class AppChallengeFrameDenied(ValueError):
    """The frame does not match the issuer-owned challenge expectation."""


@dataclass(frozen=True)
class AppChallengeExpectation:
    ceremony_id: str
    challenge_id: str
    app_instance_nonce: str


@dataclass(frozen=True)
class ParsedAppChallenge:
    ceremony_id: str
    challenge_id: str
    app_instance_nonce: str
    frame_sha256: str


def _canonical_uuid(value):
    if type(value) is not str:
        return False
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _validate_expected(expected):
    if (type(expected) is not AppChallengeExpectation
            or not all(_canonical_uuid(value) for value in (
                expected.ceremony_id, expected.challenge_id,
                expected.app_instance_nonce))
            or len({expected.ceremony_id, expected.challenge_id,
                    expected.app_instance_nonce}) != 3):
        raise AppChallengeFrameDenied("challenge expectation invalid")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise AppChallengeFrameDenied("duplicate frame field")
        value[key] = item
    return value


def encode_app_challenge_frame(expected):
    """Construct the canonical bytes; this does not authenticate their sender."""
    _validate_expected(expected)
    frame = canonical_json({
        "schema_version": SCHEMA_VERSION,
        "ceremony_id": expected.ceremony_id,
        "challenge_id": expected.challenge_id,
        "app_instance_nonce": expected.app_instance_nonce,
    }).encode("ascii")
    if len(frame) > MAX_FRAME_BYTES:
        raise AppChallengeFrameDenied("challenge frame too large")
    return frame


def parse_app_challenge_frame(raw, expected):
    """Compare one bounded canonical frame, without asserting pipe identity."""
    _validate_expected(expected)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_FRAME_BYTES:
        raise AppChallengeFrameDenied("challenge frame size invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, TypeError) as error:
        raise AppChallengeFrameDenied("challenge frame malformed") from error
    if (type(payload) is not dict or frozenset(payload) != _FIELDS
            or payload.get("schema_version") != SCHEMA_VERSION
            or type(payload.get("ceremony_id")) is not str
            or type(payload.get("challenge_id")) is not str
            or type(payload.get("app_instance_nonce")) is not str
            or raw != canonical_json(payload).encode("ascii")):
        raise AppChallengeFrameDenied("challenge frame noncanonical")
    if (payload["ceremony_id"] != expected.ceremony_id
            or payload["challenge_id"] != expected.challenge_id
            or payload["app_instance_nonce"] != expected.app_instance_nonce):
        raise AppChallengeFrameDenied("challenge frame mismatch")
    return ParsedAppChallenge(
        expected.ceremony_id, expected.challenge_id,
        expected.app_instance_nonce, hashlib.sha256(raw).hexdigest())
