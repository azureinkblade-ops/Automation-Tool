"""Isolated temp-DB qualification for request-bound one-send receipts."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tools.hermes_core.durable_kilo_send_claim_store import (
    DurableKiloSendClaimStore,
    KiloSendStoreConflict,
    KiloSendStoreIntegrityError,
    KiloSendStoreUnavailable,
)
from tests.hermes_core.test_ea4e92fm_kilo_send_claim import material


def store(tmp_path):
    return DurableKiloSendClaimStore.initialize(
        tmp_path / "send.sqlite3", anchor_path=tmp_path / "send.anchor.json")


def test_receipt_is_durable_and_reopenable(tmp_path):
    owner = store(tmp_path)
    receipt = owner.claim(material())
    assert len(receipt) == 64
    reopened = DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)
    with pytest.raises(KiloSendStoreConflict):
        reopened.claim(material())


@pytest.mark.parametrize("field,value", [
    ("request_nonce", "1" * 32),
    ("run_id", "2" * 32),
    ("execution_attempt_id", "another-attempt"),
    ("invocation_authorization_id", "another-auth"),
])
def test_reused_identity_is_denied(tmp_path, field, value):
    owner = store(tmp_path)
    owner.claim(material())
    replay = material()
    replay[field] = value
    with pytest.raises(KiloSendStoreConflict):
        owner.claim(replay)


def test_distinct_second_claim_chains(tmp_path):
    owner = store(tmp_path)
    first = owner.claim(material())
    second = material()
    second.update(run_id="1" * 32, request_nonce="2" * 32,
                  execution_attempt_id="attempt-2",
                  invocation_authorization_id="authorization-2")
    assert owner.claim(second) != first
    DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_anchor_rollback_denied(tmp_path):
    owner = store(tmp_path)
    original = owner.anchor_path.read_bytes()
    owner.claim(material())
    owner.anchor_path.write_bytes(original)
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_database_rollback_denied(tmp_path):
    owner = store(tmp_path)
    owner.claim(material())
    with sqlite3.connect(owner.path) as db:
        db.execute("DELETE FROM claims")
        db.execute("UPDATE metadata SET generation=0, head_hash=?", ("0" * 64,))
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_tampered_material_denied(tmp_path):
    owner = store(tmp_path)
    owner.claim(material())
    with sqlite3.connect(owner.path) as db:
        db.execute("UPDATE claims SET material_json=?", (json.dumps({"tampered": True}),))
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_nonobject_material_denied(tmp_path):
    owner = store(tmp_path)
    owner.claim(material())
    with sqlite3.connect(owner.path) as db:
        db.execute("UPDATE claims SET material_json='[]'")
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_commit_anchor_gap_is_fail_closed(tmp_path):
    owner = store(tmp_path)
    def crash():
        raise RuntimeError("injected crash")
    owner._after_database_commit_before_anchor = crash
    with pytest.raises(RuntimeError, match="injected crash"):
        owner.claim(material())
    with pytest.raises(KiloSendStoreIntegrityError):
        DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)


def test_concurrent_claim_has_one_winner(tmp_path):
    owner = store(tmp_path)
    peer = DurableKiloSendClaimStore(owner.path, anchor_path=owner.anchor_path)
    def attempt(candidate):
        try:
            return candidate.claim(material())
        except KiloSendStoreConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (owner, peer)))
    assert sum(value is not None for value in outcomes) == 1


def test_missing_side_cannot_be_reinitialized(tmp_path):
    owner = store(tmp_path)
    with pytest.raises(KiloSendStoreUnavailable):
        DurableKiloSendClaimStore.initialize(owner.path, anchor_path=tmp_path / "other.anchor")
