"""Parse one fake gateway event; this is not socket or execution authority."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import json
import re


class FakePendingEventDenied(ValueError):
    pass


@dataclass(frozen=True)
class FakePendingEvent:
    peer_ip: str
    body_bytes: int
    body_sha256: str


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FakePendingEventDenied("duplicate event field")
        result[key] = value
    return result


def parse_fake_pending_event(line: bytes) -> FakePendingEvent:
    """Accept only the bounded single-line event emitted by the fake gateway."""
    if type(line) is not bytes or len(line) > 512 or not line.endswith(b"\n") \
            or line.count(b"\n") != 1 or b"\r" in line:
        raise FakePendingEventDenied("event framing denied")
    try:
        payload = json.loads(line.decode("ascii"), object_pairs_hook=_unique_fields)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise FakePendingEventDenied("event JSON denied") from exc
    if (type(payload) is not dict
            or set(payload) != {"event", "peer", "body_bytes", "body_sha256"}
            or payload["event"] != "FAKE_REQUEST_PENDING"
            or type(payload["peer"]) is not str
            or type(payload["body_bytes"]) is not int
            or not 1 <= payload["body_bytes"] <= 65536
            or type(payload["body_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", payload["body_sha256"]) is None):
        raise FakePendingEventDenied("event shape denied")
    try:
        address = IPv4Address(payload["peer"])
    except ValueError as exc:
        raise FakePendingEventDenied("event peer denied") from exc
    if str(address) != payload["peer"]:
        raise FakePendingEventDenied("event peer denied")
    return FakePendingEvent(str(address), payload["body_bytes"],
                            payload["body_sha256"])
