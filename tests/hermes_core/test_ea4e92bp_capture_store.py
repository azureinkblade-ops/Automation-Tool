from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import sqlite3

import pytest

from tools.hermes_core.capture_qualification_authority import (
    CaptureArtifactInvalid, CaptureQualificationArtifact, SCHEMA_ID,
)
from tools.hermes_core.capture_qualification_store import (
    CaptureQualificationStore, CaptureStoreConflict, CaptureStoreIntegrityError,
)


TASK = b"Return exactly: EA4E92_OPENCODE_CURRENT_REPLAY_OK. Do not use tools or edit files."
NOW = "2026-09-30T00:00:01Z"
ISSUE_HASH = hashlib.sha256(b"fake externally reviewed issue request").hexdigest()


def artifact(**changes):
    payload = dict(
        schema_id=SCHEMA_ID,
        authorization_id="cap-auth:one", issue_request_id="cap-issue:one",
        approval_id="cap-approval:one", operator_id="operator:one",
        run_id="cap-run:one", receiver_id="opencode-cli-agent",
        task_sha256=hashlib.sha256(TASK).hexdigest(), source_commit="a" * 40,
        executable_sha256="b" * 64, config_sha256="c" * 64,
        transport_id="d" * 64, model_binding_id="e" * 64,
        provider_budget_id="cap-budget:one",
        issued_at="2026-09-30T00:00:00Z", expires_at="2026-09-30T00:05:00Z",
        process_start_limit=1, nonce="nonce:one",
    )
    payload.update(changes)
    return CaptureQualificationArtifact.from_mapping(payload)


def store(tmp_path):
    return CaptureQualificationStore.initialize(
        tmp_path / "capture.sqlite3", anchor_path=tmp_path / "capture.anchor.json",
        instance_id="cap-store:one",
    )


def reopen(owner, **changes):
    args = dict(
        anchor_path=owner.anchor_path,
        expected_instance_id=owner.expected_instance_id,
        expected_generation=owner.generation,
    )
    args.update(changes)
    return CaptureQualificationStore(owner.path, **args)


def claim(owner, value, **changes):
    args = dict(
        task=TASK, now=NOW, receiver_id=value.receiver_id,
        source_commit=value.source_commit,
        executable_sha256=value.executable_sha256,
        config_sha256=value.config_sha256, transport_id=value.transport_id,
        model_binding_id=value.model_binding_id,
        provider_budget_id=value.provider_budget_id,
    )
    args.update(changes)
    return owner.claim(value, **args)


def test_issue_claim_reopen_and_no_refund(tmp_path):
    owner, value = store(tmp_path), artifact()
    assert owner.persist_issued(value, issue_request_hash=ISSUE_HASH) is False
    assert owner.generation == 2
    assert reopen(owner).inspect(value.authorization_id).consumed is False
    assert claim(owner, value) is True
    assert owner.generation == 3
    resumed = reopen(owner)
    assert resumed.inspect(value.authorization_id).consumed_at == NOW
    assert claim(resumed, value) is False
    assert resumed.persist_issued(value, issue_request_hash=ISSUE_HASH) is True
    assert resumed.inspect(value.authorization_id).consumed is True


def test_exact_issue_replay_and_collision(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    assert owner.persist_issued(value, issue_request_hash=ISSUE_HASH) is True
    with pytest.raises(CaptureStoreConflict):
        owner.persist_issued(value, issue_request_hash="f" * 64)
    with pytest.raises(CaptureStoreConflict):
        owner.persist_issued(artifact(nonce="nonce:two"), issue_request_hash=ISSUE_HASH)
    with pytest.raises(CaptureStoreConflict):
        owner.persist_issued(
            artifact(authorization_id="cap-auth:two"), issue_request_hash=ISSUE_HASH,
        )


@pytest.mark.parametrize("change", [
    {"task": b"different"}, {"now": "2026-09-30T00:05:00Z"},
    {"source_commit": "f" * 40}, {"model_binding_id": "f" * 64},
    {"provider_budget_id": "other"},
])
def test_wrong_current_material_does_not_consume(tmp_path, change):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    with pytest.raises(CaptureArtifactInvalid):
        claim(owner, value, **change)
    assert owner.inspect(value.authorization_id).consumed is False
    assert claim(owner, value) is True


@pytest.mark.parametrize("mark", ["cancel", "revoke"])
def test_durable_preclaim_denial_and_postclaim_no_refund(tmp_path, mark):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    getattr(owner, mark)(value.authorization_id, at=NOW)
    state = reopen(owner).inspect(value.authorization_id)
    field = "cancelled_at" if mark == "cancel" else "revoked_at"
    assert getattr(state, field) == NOW
    assert claim(owner, value) is False
    assert state.consumed is False


def test_cancel_after_claim_keeps_credit_consumed(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    assert claim(owner, value) is True
    owner.cancel(value.authorization_id, at="2026-09-30T00:00:02Z")
    state = reopen(owner).inspect(value.authorization_id)
    assert state.consumed is True
    assert state.cancelled_at == "2026-09-30T00:00:02Z"
    assert claim(owner, value) is False


def test_claim_and_revoke_race_never_refunds_credit(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    claimant, revoker = reopen(owner), reopen(owner)

    def run_claim():
        try:
            return claim(claimant, value)
        except CaptureStoreIntegrityError:
            return False

    def run_revoke():
        try:
            revoker.revoke(value.authorization_id, at=NOW)
            return True
        except CaptureStoreIntegrityError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda action: action(), (run_claim, run_revoke)))
    assert outcomes.count(True) == 1
    state = reopen(owner, expected_generation=3).inspect(value.authorization_id)
    assert state.consumed is outcomes[0]
    assert (state.revoked_at == NOW) is outcomes[1]


def test_concurrent_claim_has_one_winner(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    first, second = reopen(owner), reopen(owner)

    def attempt(candidate):
        try:
            return claim(candidate, value)
        except CaptureStoreIntegrityError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (first, second)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert reopen(owner, expected_generation=3).inspect(value.authorization_id).consumed is True


def test_record_and_anchor_tamper_denied(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    with sqlite3.connect(owner.path) as connection:
        connection.execute(
            "UPDATE capture_authorizations SET artifact_hash=? WHERE authorization_id=?",
            ("f" * 64, value.authorization_id),
        )
    with pytest.raises(CaptureStoreIntegrityError):
        owner.inspect(value.authorization_id)

    clean = store(tmp_path / "other")
    clean.persist_issued(value, issue_request_hash=ISSUE_HASH)
    anchor = json.loads(clean.anchor_path.read_text(encoding="utf-8"))
    anchor["generation"] = 1
    clean.anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(clean)


def test_database_rollback_against_anchor_denied(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    snapshot = tmp_path / "earlier.sqlite3"
    shutil.copyfile(owner.path, snapshot)
    assert claim(owner, value) is True
    shutil.copyfile(snapshot, owner.path)
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(owner)


def test_interrupted_anchor_publication_stays_hold(tmp_path):
    owner, value = store(tmp_path), artifact()

    def interrupted():
        raise RuntimeError("simulated interruption after DB commit")

    owner._after_commit_before_anchor = interrupted
    with pytest.raises(RuntimeError, match="interruption"):
        owner.persist_issued(value, issue_request_hash=ISSUE_HASH)
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(owner)


def test_interrupted_claim_publication_does_not_refund(tmp_path):
    owner, value = store(tmp_path), artifact()
    owner.persist_issued(value, issue_request_hash=ISSUE_HASH)

    def interrupted():
        raise RuntimeError("simulated claim interruption")

    owner._after_commit_before_anchor = interrupted
    with pytest.raises(RuntimeError, match="claim interruption"):
        claim(owner, value)
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(owner)


def test_missing_anchor_does_not_self_repair(tmp_path):
    target = tmp_path / "orphan.sqlite3"
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE placeholder(value INTEGER)")
    with pytest.raises(CaptureStoreIntegrityError):
        CaptureQualificationStore(
            target, anchor_path=tmp_path / "missing.anchor.json",
            expected_instance_id="cap-store:one", expected_generation=1,
        )


def test_wrong_external_store_pin_denied(tmp_path):
    owner = store(tmp_path)
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(owner, expected_instance_id="another-store")
    with pytest.raises(CaptureStoreIntegrityError):
        reopen(owner, expected_generation=2)


def test_capture_store_is_not_production_authorization_table(tmp_path):
    owner = store(tmp_path)
    with sqlite3.connect(owner.path) as connection:
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "capture_authorizations" in names
    assert "invocation_authorizations" not in names
