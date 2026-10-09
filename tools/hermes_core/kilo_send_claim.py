"""Canonical request-bound send material; persistence owns any release receipt."""

from ipaddress import IPv4Address
from datetime import datetime, timezone
import re

from tools.hermes_core.hashing import sha256_payload


SCHEMA = "hermes.ea4e-kilo-send-claim/v1"
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {
    "run_id", "delegation_id", "execution_attempt_id",
    "invocation_authorization_id", "request_nonce", "source_commit",
    "network_id", "gateway_id", "receiver_id", "peer_ip",
    "body_sha256", "body_bytes", "claimed_at",
}


class KiloSendClaimDenied(ValueError):
    pass


def canonical_send_claim_material(values):
    """Validate exact material; this candidate is not a durable claim."""
    if type(values) is not dict or set(values) != _FIELDS:
        raise KiloSendClaimDenied("claim fields denied")
    for name in ("delegation_id", "execution_attempt_id",
                 "invocation_authorization_id"):
        value = values[name]
        if type(value) is not str or not value or len(value) > 256:
            raise KiloSendClaimDenied("claim authority identity denied")
    for name, pattern in (("run_id", _HEX32), ("request_nonce", _HEX32),
                          ("source_commit", _HEX40), ("network_id", _HEX64),
                          ("gateway_id", _HEX64), ("receiver_id", _HEX64),
                          ("body_sha256", _HEX64)):
        value = values[name]
        if type(value) is not str or pattern.fullmatch(value) is None:
            raise KiloSendClaimDenied("claim identity denied")
    if len({values["network_id"], values["gateway_id"],
            values["receiver_id"]}) != 3:
        raise KiloSendClaimDenied("claim identity collision")
    try:
        peer = IPv4Address(values["peer_ip"])
    except (TypeError, ValueError) as exc:
        raise KiloSendClaimDenied("claim peer denied") from exc
    if str(peer) != values["peer_ip"]:
        raise KiloSendClaimDenied("claim peer denied")
    size = values["body_bytes"]
    if type(size) is not int or not 1 <= size <= 65536:
        raise KiloSendClaimDenied("claim body size denied")
    claimed_at = values["claimed_at"]
    if (type(claimed_at) is not str or
            re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z",
                         claimed_at) is None):
        raise KiloSendClaimDenied("claim timestamp denied")
    try:
        parsed = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KiloSendClaimDenied("claim timestamp denied") from exc
    if parsed.tzinfo != timezone.utc:
        raise KiloSendClaimDenied("claim timestamp denied")
    return {"schema": SCHEMA, **values}


def candidate_send_claim_hash(values):
    """Hash canonical material for a future store; not a release receipt."""
    return sha256_payload(canonical_send_claim_material(values))


def assert_pending_matches_claim(pending, values):
    """Check the accepted pending header against exact claim material."""
    material = canonical_send_claim_material(values)
    fields = ("run_id", "request_nonce", "source_commit", "network_id",
              "gateway_id", "receiver_id", "peer_ip", "body_sha256",
              "body_bytes")
    if type(pending) is not dict or pending.get("kind") != "pending" or any(
            pending.get(name) != material[name] for name in fields):
        raise KiloSendClaimDenied("pending request and claim differ")
