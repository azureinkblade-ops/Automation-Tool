"""Pure control-frame authentication; no Docker, receiver, or model."""

from copy import deepcopy
import hashlib
import hmac

import pytest

from tools.hermes_core.kilo_control_frame import (
    DOMAIN, KiloControlFrameDenied, SCHEMA,
    decode_control_frame, encode_control_frame,
)


KEY = b"k" * 32
BODY = b'{"model":"ea4e-inert"}'


def pending():
    return {"schema": SCHEMA, "kind": "pending", "run_id": "a" * 32,
            "request_nonce": "b" * 32, "source_commit": "c" * 40,
            "network_id": "1" * 64, "gateway_id": "2" * 64,
            "receiver_id": "3" * 64, "peer_ip": "172.20.0.2",
            "body_sha256": hashlib.sha256(BODY).hexdigest(),
            "body_bytes": len(BODY), "sequence": 1}


def release():
    header = pending()
    header.update(kind="release", sequence=2,
                  claim_receipt_hash="d" * 64, response_sha256="e" * 64)
    return header


def test_pending_and_release_round_trip_are_non_authoritative():
    assert decode_control_frame(encode_control_frame(pending(), BODY, KEY), KEY) \
        == (pending(), BODY)
    assert decode_control_frame(encode_control_frame(release(), b"", KEY), KEY) \
        == (release(), b"")


@pytest.mark.parametrize("mutate", [
    lambda h: h.update(body_bytes=len(BODY) + 1),
    lambda h: h.update(body_sha256="0" * 64),
    lambda h: h.update(sequence=True),
    lambda h: h.update(peer_ip="127.0.0.01"),
    lambda h: h.update(gateway_id=h["receiver_id"]),
    lambda h: h.update(source_commit="bad"),
    lambda h: h.update(extra="field"),
])
def test_bad_pending_fields_denied_before_encoding(mutate):
    header = deepcopy(pending())
    mutate(header)
    with pytest.raises(KiloControlFrameDenied):
        encode_control_frame(header, BODY, KEY)


@pytest.mark.parametrize("mutate", [
    lambda h: h.update(sequence=1),
    lambda h: h.update(claim_receipt_hash="bad"),
    lambda h: h.pop("response_sha256"),
])
def test_bad_release_fields_denied(mutate):
    header = release()
    mutate(header)
    with pytest.raises(KiloControlFrameDenied):
        encode_control_frame(header, b"", KEY)
    with pytest.raises(KiloControlFrameDenied):
        encode_control_frame(release(), BODY, KEY)


def test_wrong_key_or_tampered_body_denied():
    frame = encode_control_frame(pending(), BODY, KEY)
    with pytest.raises(KiloControlFrameDenied, match="authentication"):
        decode_control_frame(frame, b"x" * 32)
    tampered = bytearray(frame)
    tampered[-33] ^= 1
    with pytest.raises(KiloControlFrameDenied, match="authentication"):
        decode_control_frame(bytes(tampered), KEY)


def test_noncanonical_signed_header_denied():
    frame = encode_control_frame(pending(), BODY, KEY)
    header_len = int.from_bytes(frame[:4], "big")
    raw = frame[4:4 + header_len]
    modified = raw.replace(b'"schema":', b'"schema" :', 1)
    payload = (len(modified).to_bytes(4, "big") + modified
               + frame[4 + header_len:-32])
    tag = hmac.digest(KEY, DOMAIN + payload, "sha256")
    with pytest.raises(KiloControlFrameDenied, match="noncanonical"):
        decode_control_frame(payload + tag, KEY)


def test_bad_length_and_key_denied():
    frame = encode_control_frame(pending(), BODY, KEY)
    with pytest.raises(KiloControlFrameDenied):
        decode_control_frame(frame[:20], KEY)
    with pytest.raises(KiloControlFrameDenied):
        decode_control_frame(frame + b"x", KEY)
    with pytest.raises(KiloControlFrameDenied):
        encode_control_frame(pending(), BODY, b"short")


def test_body_cap_and_empty_pending_are_denied():
    for body in (b"", b"x" * 65537):
        header = pending()
        header["body_bytes"] = len(body)
        header["body_sha256"] = hashlib.sha256(body).hexdigest()
        with pytest.raises(KiloControlFrameDenied, match="body size"):
            encode_control_frame(header, body, KEY)


def test_duplicate_signed_json_field_denied():
    frame = encode_control_frame(pending(), BODY, KEY)
    header_len = int.from_bytes(frame[:4], "big")
    raw = frame[4:4 + header_len]
    modified = raw[:-1] + b',"schema":"' + SCHEMA.encode() + b'"}'
    payload = (len(modified).to_bytes(4, "big") + modified
               + frame[4 + header_len:-32])
    tag = hmac.digest(KEY, DOMAIN + payload, "sha256")
    with pytest.raises(KiloControlFrameDenied, match="noncanonical"):
        decode_control_frame(payload + tag, KEY)
