"""Networkless two-store sequence proof; no production release path."""

import hashlib

import pytest

from tools.ea4e92dw_kilo_dynamic_fake_gateway import (
    DynamicFakeScope,
    provision_dynamic_fake_budget,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.durable_kilo_send_claim_store import (
    DurableKiloSendClaimStore,
    KiloSendStoreIntegrityError,
)
from tools.hermes_core.kilo_control_frame import (
    SCHEMA, decode_control_frame, encode_control_frame,
)
from tools.hermes_core.kilo_send_claim import (
    KiloSendClaimDenied,
    assert_pending_matches_claim,
)


KEY = b"k" * 32
BODY = b'{"model":"ea4e-inert"}'
NOW = "2026-10-08T20:00:00Z"


def fixture(tmp_path):
    scope = DynamicFakeScope(
        run_id="a" * 32, source_commit="b" * 40,
        transport_id="c" * 64, model_binding_id="d" * 64,
        task_hash="e" * 64, network_id="1" * 64,
        container_id="3" * 64, token_sha256="f" * 64,
        issued_at="2026-10-08T19:59:00Z",
        expires_at="2026-10-08T20:01:00Z",
    )
    auth = DurableInvocationAuthorizationStore.initialize(
        tmp_path / "auth.sqlite3", anchor_path=tmp_path / "auth.anchor.json")
    provision_dynamic_fake_budget(auth, scope)
    send = DurableKiloSendClaimStore.initialize(
        tmp_path / "send.sqlite3", anchor_path=tmp_path / "send.anchor.json")
    values = {
        "run_id": scope.run_id, "delegation_id": "fake-delegation-1",
        "execution_attempt_id": "fake-attempt-1",
        "invocation_authorization_id": scope.payload()["invocation_authorization_id"],
        "request_nonce": "2" * 32, "source_commit": scope.source_commit,
        "network_id": scope.network_id, "gateway_id": "4" * 64,
        "receiver_id": scope.container_id, "peer_ip": "172.20.0.2",
        "body_sha256": hashlib.sha256(BODY).hexdigest(),
        "body_bytes": len(BODY), "claimed_at": NOW,
    }
    header_fields = ("run_id", "request_nonce", "source_commit", "network_id",
                     "gateway_id", "receiver_id", "peer_ip", "body_sha256",
                     "body_bytes")
    pending = {"schema": SCHEMA, "kind": "pending", "sequence": 1,
               **{name: values[name] for name in header_fields}}
    return scope, auth, send, values, pending


def fake_claim(auth, send, scope, values, frame, *, after_invocation=None):
    pending, body = decode_control_frame(frame, KEY)
    assert body == BODY
    assert_pending_matches_claim(pending, values)
    assert scope.payload()["invocation_authorization_id"] == values["invocation_authorization_id"]
    assert scope.payload()["runtime_scope"] == "qualification-only"
    result = auth.claim(scope.payload(), consumed_at=NOW,
                        validate=lambda: assert_pending_matches_claim(pending, values))
    if not result.allowed:
        raise RuntimeError("fake invocation denied")
    if after_invocation:
        after_invocation()
    return send.claim(values)


def test_two_durable_claims_can_bind_a_fake_release(tmp_path):
    scope, auth, send, values, pending = fixture(tmp_path)
    frame = encode_control_frame(pending, BODY, KEY)
    receipt = fake_claim(auth, send, scope, values, frame)
    assert auth.consumed_count() == 1
    release = {**pending, "kind": "release", "sequence": 2,
               "claim_receipt_hash": receipt, "response_sha256": "0" * 64}
    decoded, released_body = decode_control_frame(
        encode_control_frame(release, b"", KEY), KEY)
    assert decoded["claim_receipt_hash"] == receipt
    assert released_body == b""


def test_mismatched_pending_denies_before_any_claim(tmp_path):
    scope, auth, send, values, pending = fixture(tmp_path)
    pending["request_nonce"] = "5" * 32
    with pytest.raises(KiloSendClaimDenied):
        fake_claim(auth, send, scope, values,
                   encode_control_frame(pending, BODY, KEY))
    assert auth.consumed_count() == 0


def test_failure_between_claims_is_consumed_without_release(tmp_path):
    scope, auth, send, values, pending = fixture(tmp_path)
    frame = encode_control_frame(pending, BODY, KEY)
    with pytest.raises(RuntimeError, match="injected interruption"):
        fake_claim(auth, send, scope, values, frame,
                   after_invocation=lambda: (_ for _ in ()).throw(
                       RuntimeError("injected interruption")))
    assert auth.consumed_count() == 1
    with pytest.raises(RuntimeError, match="fake invocation denied"):
        fake_claim(auth, send, scope, values, frame)


def test_send_anchor_gap_is_consumed_and_cannot_release(tmp_path):
    scope, auth, send, values, pending = fixture(tmp_path)
    def crash():
        raise RuntimeError("injected anchor gap")
    send._after_database_commit_before_anchor = crash
    with pytest.raises(RuntimeError, match="injected anchor gap"):
        fake_claim(auth, send, scope, values,
                   encode_control_frame(pending, BODY, KEY))
    assert auth.consumed_count() == 1
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(send.path, anchor_path=send.anchor_path)
