"""Strict versioned fake Kilo ping event; parsing grants no release authority."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import json
import re


class PingPendingEventDenied(ValueError):
    pass


@dataclass(frozen=True)
class PingPendingEvent:
    attempt_id: str
    response_sha256: str
    peer_ip: str
    body_bytes: int
    body_sha256: str


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PingPendingEventDenied("duplicate event field")
        value[key] = item
    return value


def parse_ping_pending_event(line: bytes, *, attempt_id: str,
                             response_sha256: str) -> PingPendingEvent:
    """Bind one bounded stdout line to the preconfigured attempt and response."""
    if (type(line) is not bytes or not 0 < len(line) <= 512
            or not line.endswith(b"\n") or line.count(b"\n") != 1
            or b"\r" in line or type(attempt_id) is not str
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", attempt_id) is None
            or type(response_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", response_sha256) is None):
        raise PingPendingEventDenied("event framing or binding denied")
    try:
        payload = json.loads(line.decode("ascii"), object_pairs_hook=_unique)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PingPendingEventDenied("event JSON denied") from exc
    if (type(payload) is not dict
            or set(payload) != {
                "event", "attempt_id", "response_sha256", "peer",
                "body_bytes", "body_sha256",
            }
            or payload["event"] != "FAKE_PING_REQUEST_PENDING"
            or payload["attempt_id"] != attempt_id
            or payload["response_sha256"] != response_sha256
            or type(payload["peer"]) is not str
            or type(payload["body_bytes"]) is not int
            or not 1 <= payload["body_bytes"] <= 65536
            or type(payload["body_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", payload["body_sha256"]) is None):
        raise PingPendingEventDenied("event shape or lineage denied")
    try:
        address = IPv4Address(payload["peer"])
    except ValueError as exc:
        raise PingPendingEventDenied("event peer denied") from exc
    if str(address) != payload["peer"]:
        raise PingPendingEventDenied("event peer denied")
    return PingPendingEvent(
        attempt_id, response_sha256, str(address),
        payload["body_bytes"], payload["body_sha256"],
    )
