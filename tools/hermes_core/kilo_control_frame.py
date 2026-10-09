"""Pure authenticated frames for a future request-scoped fake gateway."""

import hashlib
import hmac
from ipaddress import IPv4Address
import json
import re


SCHEMA = "hermes.ea4e-kilo-control/v1"
DOMAIN = b"EA4E-KILO-CONTROL-V1\x00"
MAX_BODY = 65536
MAX_HEADER = 2048
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_BASE = {"schema", "kind", "run_id", "request_nonce", "source_commit",
         "network_id", "gateway_id", "receiver_id", "peer_ip",
         "body_sha256", "body_bytes", "sequence"}


class KiloControlFrameDenied(ValueError):
    pass


def _canonical(header):
    return json.dumps(header, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _validate(header, body):
    if type(header) is not dict or type(body) is not bytes:
        raise KiloControlFrameDenied("frame input denied")
    kind = header.get("kind")
    fields = _BASE if kind == "pending" else _BASE | {
        "claim_receipt_hash", "response_sha256"} if kind == "release" else None
    if fields is None or set(header) != fields or header["schema"] != SCHEMA:
        raise KiloControlFrameDenied("frame shape denied")
    for name, pattern in (("run_id", _HEX32), ("request_nonce", _HEX32),
                          ("source_commit", _HEX40), ("network_id", _HEX64),
                          ("gateway_id", _HEX64), ("receiver_id", _HEX64),
                          ("body_sha256", _HEX64)):
        value = header[name]
        if type(value) is not str or pattern.fullmatch(value) is None:
            raise KiloControlFrameDenied("frame identity denied")
    if len({header["network_id"], header["gateway_id"],
            header["receiver_id"]}) != 3:
        raise KiloControlFrameDenied("frame identity collision")
    try:
        peer = IPv4Address(header["peer_ip"])
    except (ValueError, TypeError) as exc:
        raise KiloControlFrameDenied("socket peer denied") from exc
    if str(peer) != header["peer_ip"]:
        raise KiloControlFrameDenied("socket peer denied")
    size = header["body_bytes"]
    if type(size) is not int or not 1 <= size <= MAX_BODY:
        raise KiloControlFrameDenied("body size denied")
    if type(header["sequence"]) is not int:
        raise KiloControlFrameDenied("sequence denied")
    if kind == "pending":
        if (header["sequence"] != 1 or len(body) != size
                or hashlib.sha256(body).hexdigest() != header["body_sha256"]):
            raise KiloControlFrameDenied("pending body denied")
    else:
        if header["sequence"] != 2 or body:
            raise KiloControlFrameDenied("release body denied")
        for name in ("claim_receipt_hash", "response_sha256"):
            value = header[name]
            if type(value) is not str or _HEX64.fullmatch(value) is None:
                raise KiloControlFrameDenied("release identity denied")


def encode_control_frame(header, body, key):
    """Encode one bounded frame; caller owns key lifecycle and replay state."""
    if type(key) is not bytes or len(key) != 32:
        raise KiloControlFrameDenied("control key denied")
    _validate(header, body)
    raw_header = _canonical(header)
    if len(raw_header) > MAX_HEADER:
        raise KiloControlFrameDenied("header length denied")
    payload = (len(raw_header).to_bytes(4, "big") + raw_header
               + len(body).to_bytes(4, "big") + body)
    tag = hmac.digest(key, DOMAIN + payload, "sha256")
    return payload + tag


def decode_control_frame(frame, key):
    """Authenticate before decoding; a valid frame is not execution authority."""
    if type(frame) is not bytes or type(key) is not bytes or len(key) != 32:
        raise KiloControlFrameDenied("control input denied")
    if len(frame) < 40 or len(frame) > 4 + MAX_HEADER + 4 + MAX_BODY + 32:
        raise KiloControlFrameDenied("frame length denied")
    header_len = int.from_bytes(frame[:4], "big")
    if not 1 <= header_len <= MAX_HEADER or len(frame) < 4 + header_len + 36:
        raise KiloControlFrameDenied("header length denied")
    body_offset = 4 + header_len
    body_len = int.from_bytes(frame[body_offset:body_offset + 4], "big")
    if body_len > MAX_BODY or len(frame) != body_offset + 4 + body_len + 32:
        raise KiloControlFrameDenied("body length denied")
    payload, tag = frame[:-32], frame[-32:]
    if not hmac.compare_digest(hmac.digest(key, DOMAIN + payload, "sha256"), tag):
        raise KiloControlFrameDenied("frame authentication denied")
    raw_header = frame[4:body_offset]
    try:
        header = json.loads(raw_header.decode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise KiloControlFrameDenied("header JSON denied") from exc
    if type(header) is not dict or _canonical(header) != raw_header:
        raise KiloControlFrameDenied("noncanonical header denied")
    body = frame[body_offset + 4:-32]
    _validate(header, body)
    return header, body
