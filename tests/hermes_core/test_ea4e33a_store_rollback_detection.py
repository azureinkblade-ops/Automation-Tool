"""EA-4E.33A durable-store rollback detection qualification, fake-only."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    AUTH_STORE_ANCHOR_SCHEMA_ID,
    AUTH_STORE_ANCHOR_SCHEMA_VERSION,
    DurableAuthorizationStoreError,
    DurableAuthorizationStoreIntegrityError,
    DurableAuthorizationStoreUnavailable,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.governed_production_caller import (
    compute_ea4e29_caller_contract_id,
)
from tools.hermes_core.governed_production_runtime import (
    compute_ea4e26_integration_contract_id,
)
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingHandle,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
    ProductionInvocationAuthorizationPolicy,
    compute_ea4e23_invocation_contract_id,
    ea4e23_invocation_contract_payload,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    compute_ea4e28_issuer_contract_id,
)


NOW = "2026-01-01T00:00:00Z"
AFTER_EXPIRY = "2026-01-01T00:10:00Z"
PROCESS_HELPER = (
    Path(__file__).resolve().parent / "fixtures" / "durable_auth_process_helper.py"
)


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    hits = {"executor": 0, "adapter": 0, "process": 0}

    def reject(category):
        def tripwire(*args, **kwargs):
            hits[category] += 1
            raise AssertionError(f"EA4E33A_REAL_{category.upper()}_TRIPWIRE")
        return tripwire

    monkeypatch.setattr(RealKiloProductionExecutor, "__init__", reject("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "__init__", reject("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", reject("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", reject("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", reject("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", reject("process"))
    yield hits
    assert hits == {"executor": 0, "adapter": 0, "process": 0}


def paths(root: Path, name: str = "auth") -> tuple[Path, Path]:
    return root / f"{name}.sqlite3", root / f"{name}.anchor.json"


def initialize(root: Path, name: str = "auth"):
    database, anchor = paths(root, name)
    return DurableInvocationAuthorizationStore.initialize(
        database, anchor_path=anchor
    )


def reopen(root: Path, name: str = "auth"):
    database, anchor = paths(root, name)
    return DurableInvocationAuthorizationStore(database, anchor_path=anchor)


def authorization(**changes):
    values = {
        "invocation_authorization_id": "auth-001",
        "receiver_id": "kilo-cli-agent",
        "binding_id": "binding-kilo-cli-agent",
        "enablement_id": "enablement-kilo-cli-agent",
        "execution_request_id": "request-001",
        "attempt_number": 1,
        "issued_at": NOW,
        "expires_at": "2026-01-01T00:05:00Z",
        "runtime_scope": "production",
        "delegation_class": "governed",
        "nonce": "nonce-001",
    }
    values.update(changes)
    return values


def persist(store, payload=None):
    payload = payload or authorization()
    return store.persist_issued(
        issue_request_id=f"issue-{payload['invocation_authorization_id']}",
        issue_request_hash=sha256_payload(payload),
        authorization_payload=payload,
    )


def claim(store, payload=None):
    return store.claim(
        payload or authorization(), consumed_at=NOW, validate=lambda: None
    )


def read_anchor(anchor: Path):
    return json.loads(anchor.read_text(encoding="utf-8"))


def write_anchor(anchor: Path, payload: dict):
    material = {
        "schema_id": payload["schema_id"],
        "schema_version": payload["schema_version"],
        "store_instance_id": payload["store_instance_id"],
        "store_generation": payload["store_generation"],
    }
    payload = {**material, "anchor_hash": sha256_payload(material)}
    anchor.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def copy_pair(root: Path, source: str, destination: str):
    source_db, source_anchor = paths(root, source)
    destination_db, destination_anchor = paths(root, destination)
    shutil.copy2(source_db, destination_db)
    shutil.copy2(source_anchor, destination_anchor)


def test_store_identity_persists_across_reopen(tmp_path):
    store = initialize(tmp_path)
    identity = store.store_instance_id
    assert reopen(tmp_path).store_instance_id == identity


def test_store_identity_is_not_path_derived(tmp_path):
    first = initialize(tmp_path, "first")
    second = initialize(tmp_path, "second")
    assert first.store_instance_id != second.store_instance_id


def test_store_identity_is_immutable_across_mutations(tmp_path):
    store = initialize(tmp_path)
    identity = store.store_instance_id
    persist(store)
    claim(store)
    assert reopen(tmp_path).store_instance_id == identity


def test_expected_identity_matches_database(tmp_path):
    store = initialize(tmp_path)
    anchor = read_anchor(paths(tmp_path)[1])
    assert anchor["store_instance_id"] == store.store_instance_id


def test_unrelated_valid_database_replacement_is_rejected(tmp_path):
    initialize(tmp_path, "primary")
    initialize(tmp_path, "other")
    shutil.copy2(paths(tmp_path, "other")[0], paths(tmp_path, "primary")[0])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path, "primary")


def test_newly_initialized_database_replacement_is_rejected(tmp_path):
    primary = initialize(tmp_path, "primary")
    persist(primary)
    initialize(tmp_path, "empty")
    shutil.copy2(paths(tmp_path, "empty")[0], paths(tmp_path, "primary")[0])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path, "primary")


def test_missing_established_anchor_is_rejected(tmp_path):
    initialize(tmp_path)
    paths(tmp_path)[1].unlink()
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        reopen(tmp_path)


def test_initialize_does_not_recreate_missing_established_anchor(tmp_path):
    initialize(tmp_path)
    database, anchor = paths(tmp_path)
    anchor.unlink()
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        DurableInvocationAuthorizationStore.initialize(
            database, anchor_path=anchor
        )
    assert not anchor.exists()


def test_database_and_anchor_paths_must_be_distinct(tmp_path):
    same_path = tmp_path / "same"
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        DurableInvocationAuthorizationStore.initialize(
            same_path, anchor_path=same_path
        )


def test_deleted_established_database_is_not_recreated(tmp_path):
    initialize(tmp_path)
    database, _ = paths(tmp_path)
    database.unlink()
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        reopen(tmp_path)
    assert not database.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: "not-json",
        lambda value: json.dumps({"schema_id": value["schema_id"]}),
        lambda value: json.dumps({**value, "schema_version": "999"}),
        lambda value: json.dumps({**value, "store_generation": "bad"}),
        lambda value: json.dumps({**value, "anchor_hash": "tampered"}),
    ],
)
def test_anchor_corruption_fails_closed(tmp_path, mutation):
    initialize(tmp_path)
    anchor = paths(tmp_path)[1]
    value = read_anchor(anchor)
    anchor.write_text(mutation(value), encoding="utf-8")
    with pytest.raises(DurableAuthorizationStoreError):
        reopen(tmp_path)


def test_anchor_schema_is_explicit_and_versioned(tmp_path):
    initialize(tmp_path)
    anchor = read_anchor(paths(tmp_path)[1])
    assert anchor["schema_id"] == AUTH_STORE_ANCHOR_SCHEMA_ID
    assert anchor["schema_version"] == AUTH_STORE_ANCHOR_SCHEMA_VERSION


def test_generation_advances_for_issue_and_claim(tmp_path):
    store = initialize(tmp_path)
    assert store.store_generation == 1
    persist(store)
    assert store.store_generation == 2
    claim(store)
    assert store.store_generation == 3


def test_idempotent_issue_replay_does_not_advance_generation(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    generation = store.store_generation
    persist(store)
    assert store.store_generation == generation


def test_stale_same_lineage_database_is_rejected(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    stale_db = tmp_path / "stale.sqlite3"
    shutil.copy2(paths(tmp_path)[0], stale_db)
    claim(store)
    shutil.copy2(stale_db, paths(tmp_path)[0])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path)


def test_stale_anchor_with_newer_database_is_rejected(tmp_path):
    store = initialize(tmp_path)
    stale_anchor = tmp_path / "stale.anchor.json"
    shutil.copy2(paths(tmp_path)[1], stale_anchor)
    persist(store)
    shutil.copy2(stale_anchor, paths(tmp_path)[1])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path)


def test_stale_backup_cannot_resurrect_consumed_authorization(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    stale_db = tmp_path / "pre-consume.sqlite3"
    shutil.copy2(paths(tmp_path)[0], stale_db)
    assert claim(store).allowed
    shutil.copy2(stale_db, paths(tmp_path)[0])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path)


def test_current_database_and_anchor_reopen(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    assert reopen(tmp_path).count() == 1


def test_current_pair_can_be_copied_together(tmp_path):
    store = initialize(tmp_path, "primary")
    persist(store)
    claim(store)
    copy_pair(tmp_path, "primary", "backup")
    assert reopen(tmp_path, "backup").consumed_count() == 1


def test_raw_database_only_backup_is_rejected(tmp_path):
    initialize(tmp_path, "primary")
    shutil.copy2(paths(tmp_path, "primary")[0], paths(tmp_path, "backup")[0])
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        reopen(tmp_path, "backup")


def test_unrelated_anchor_replacement_is_rejected(tmp_path):
    initialize(tmp_path, "primary")
    initialize(tmp_path, "other")
    shutil.copy2(paths(tmp_path, "other")[1], paths(tmp_path, "primary")[1])
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path, "primary")


def test_both_database_and_anchor_rollback_share_external_trust_boundary(tmp_path):
    store = initialize(tmp_path, "primary")
    persist(store)
    copy_pair(tmp_path, "primary", "stale")
    claim(store)
    shutil.copy2(paths(tmp_path, "stale")[0], paths(tmp_path, "primary")[0])
    shutil.copy2(paths(tmp_path, "stale")[1], paths(tmp_path, "primary")[1])
    assert reopen(tmp_path, "primary").consumed_count() == 0


class CrashAfterDatabaseCommit(DurableInvocationAuthorizationStore):
    def _after_database_commit_before_anchor(self):
        raise RuntimeError("simulated crash after database commit")


def test_crash_between_database_and_anchor_fails_closed(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    crashing = CrashAfterDatabaseCommit(
        paths(tmp_path)[0], anchor_path=paths(tmp_path)[1]
    )
    with pytest.raises(DurableAuthorizationStoreError):
        claim(crashing)
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        reopen(tmp_path)


def test_concurrent_crash_ambiguity_allows_no_second_claim(tmp_path):
    store = initialize(tmp_path)
    persist(store)
    crashing = CrashAfterDatabaseCommit(
        paths(tmp_path)[0], anchor_path=paths(tmp_path)[1]
    )
    with pytest.raises(DurableAuthorizationStoreError):
        claim(crashing)
    with pytest.raises(DurableAuthorizationStoreIntegrityError):
        DurableInvocationAuthorizationStore(
            paths(tmp_path)[0], anchor_path=paths(tmp_path)[1]
        )


def test_anchor_write_permission_failure_returns_no_allow(tmp_path, monkeypatch):
    store = initialize(tmp_path)
    persist(store)

    def denied_replace(*args, **kwargs):
        raise PermissionError("anchor is read-only")

    monkeypatch.setattr(os, "replace", denied_replace)
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        claim(store)


def test_paths_are_explicit_and_not_task_derived(tmp_path):
    database, anchor = paths(tmp_path)
    store = DurableInvocationAuthorizationStore.initialize(
        database, anchor_path=anchor
    )
    assert store.path == database.resolve()
    assert store.anchor_path == anchor.resolve()


def test_multiprocess_claim_allows_exactly_one_and_anchor_remains_consistent(tmp_path):
    store = initialize(tmp_path)
    payload = authorization()
    persist(store, payload)
    database, anchor = paths(tmp_path)
    argv = [
        sys.executable,
        str(PROCESS_HELPER),
        "claim",
        str(database),
        str(anchor),
        json.dumps(payload),
        NOW,
    ]
    processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    results = [process.communicate(timeout=15)[0].strip() for process in processes]
    assert results.count("ALLOW") == 1
    assert set(results) <= {"ALLOW", "DENY", "ERROR"}
    assert reopen(tmp_path).consumed_count() == 1


def test_clock_rollback_behavior_matches_current_clock_contract(tmp_path):
    store = initialize(tmp_path)
    payload = authorization()
    persist(store, payload)
    auth = ProductionInvocationAuthorization(**payload)
    handle = ProductionExecutorBindingHandle(
        binding_id=payload["binding_id"],
        enablement_id=payload["enablement_id"],
        receiver_id=payload["receiver_id"],
        executor_identity=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_identity"],
        bound_at=NOW,
        expires_at="2026-01-01T01:00:00Z",
        registry=ExecutorRegistry(),
    )
    expired = ProductionInvocationAuthorizationPolicy(
        clock=BindingClock(now=AFTER_EXPIRY), store=reopen(tmp_path)
    ).evaluate(auth, handle, {})
    assert expired.policy_reason == "INVOCATION_AUTHORIZATION_EXPIRED"
    before_expiry = ProductionInvocationAuthorizationPolicy(
        clock=BindingClock(now=NOW), store=reopen(tmp_path)
    ).evaluate(auth, handle, {})
    assert before_expiry.policy_decision == "ALLOW"
    assert ea4e23_invocation_contract_payload()["expiry_rechecked_against_current_clock_after_restart"] is True


def test_sealed_contract_chain_is_unchanged():
    assert compute_ea4e23_invocation_contract_id() == "e638e8ff695172eceaf5c36baa1f5063633b32e344971a7d6fc54cf456faff91"
    assert compute_ea4e26_integration_contract_id() == "84aad8495a6ec034c763f8c62a98ec41e85ef48c2b453bd098bc3cf57f624a67"
    assert compute_ea4e28_issuer_contract_id() == "395944480c5ea2cde374b07093f07b6e44633f404abb8e420136ee5516b910e1"
    assert compute_ea4e29_caller_contract_id() == "821941da6ea4b08105c359afeb86193e343a429b0a74a32826bd6370faaa5166"
