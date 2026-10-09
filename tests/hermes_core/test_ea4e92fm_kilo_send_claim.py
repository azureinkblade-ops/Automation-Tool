"""Pure validation for a future durable request-bound send claim."""

import pytest

from tools.hermes_core.kilo_send_claim import (
    KiloSendClaimDenied,
    assert_pending_matches_claim,
    candidate_send_claim_hash,
    canonical_send_claim_material,
)
from tools.hermes_core.kilo_control_frame import SCHEMA as CONTROL_SCHEMA


def material():
    return {
        "run_id": "a" * 32,
        "delegation_id": "delegation-1",
        "execution_attempt_id": "attempt-1",
        "invocation_authorization_id": "authorization-1",
        "request_nonce": "b" * 32,
        "source_commit": "c" * 40,
        "network_id": "d" * 64,
        "gateway_id": "e" * 64,
        "receiver_id": "f" * 64,
        "peer_ip": "172.20.0.3",
        "body_sha256": "0" * 64,
        "body_bytes": 100,
        "claimed_at": "2026-10-08T20:00:00Z",
    }


def test_canonical_material_is_stable_and_domain_separated():
    claim = material()
    assert canonical_send_claim_material(claim)["schema"].endswith("/v1")
    assert candidate_send_claim_hash(claim) == candidate_send_claim_hash(dict(reversed(list(claim.items()))))


@pytest.mark.parametrize("field,value", [
    ("run_id", "A" * 32), ("request_nonce", "short"),
    ("source_commit", "c" * 39), ("body_sha256", "x" * 64),
    ("delegation_id", ""), ("execution_attempt_id", None),
    ("invocation_authorization_id", "x" * 257),
    ("peer_ip", "172.020.0.3"), ("body_bytes", True),
    ("body_bytes", 65537), ("claimed_at", "today"),
    ("claimed_at", "2026-02-30T20:00:00Z"),
])
def test_bad_material_is_denied(field, value):
    claim = material()
    claim[field] = value
    with pytest.raises(KiloSendClaimDenied):
        canonical_send_claim_material(claim)


def test_unknown_field_and_colliding_id_denied():
    claim = material()
    claim["extra"] = 1
    with pytest.raises(KiloSendClaimDenied):
        canonical_send_claim_material(claim)
    claim = material()
    claim["gateway_id"] = claim["receiver_id"]
    with pytest.raises(KiloSendClaimDenied):
        canonical_send_claim_material(claim)


def test_pending_must_match_exact_request():
    claim = material()
    header_fields = ("run_id", "request_nonce", "source_commit", "network_id",
                     "gateway_id", "receiver_id", "peer_ip", "body_sha256",
                     "body_bytes")
    pending = {"schema": CONTROL_SCHEMA, "kind": "pending", "sequence": 1,
               **{key: claim[key] for key in header_fields}}
    assert_pending_matches_claim(pending, claim)
    pending["body_sha256"] = "1" * 64
    with pytest.raises(KiloSendClaimDenied):
        assert_pending_matches_claim(pending, claim)
    pending["body_sha256"] = claim["body_sha256"]
    pending["extra"] = True
    with pytest.raises(KiloSendClaimDenied):
        assert_pending_matches_claim(pending, claim)
