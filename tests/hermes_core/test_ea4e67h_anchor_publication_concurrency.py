"""Deterministic claim/anchor publication qualification, fake-only."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import sqlite3

import pytest

from tests.hermes_core.test_ea4e32_restart_durable_authorization import (
    NOW, authorization, initialize_store, open_store, persist,
)
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore, DurableAuthorizationStoreUnavailable,
)


@pytest.mark.parametrize("reopen", [False, True])
def test_competing_claim_waits_for_anchor_publication(tmp_path, monkeypatch, reopen):
    path = tmp_path / "authorization.sqlite3"
    store = initialize_store(path)
    payload = authorization().to_canonical_dict()
    persist(store)
    committed = threading.Event()
    release = threading.Event()
    reader_started = threading.Event()

    def pause():
        committed.set()
        assert release.wait(5), "test must release anchor publication"

    monkeypatch.setattr(store, "_after_database_commit_before_anchor", pause)

    def competing_claim():
        reader_started.set()
        reader = open_store(path) if reopen else store
        return reader.claim(payload, consumed_at=NOW, validate=lambda: None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.claim, payload, consumed_at=NOW, validate=lambda: None)
        try:
            assert committed.wait(5)
            second = pool.submit(competing_claim)
            assert reader_started.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.1)
        finally:
            release.set()
        assert first.result(timeout=5).allowed is True
        rejected = second.result(timeout=5)
        assert rejected.allowed is False
        assert rejected.reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


def test_coordination_path_collision_rejected_before_initialization(tmp_path):
    path = tmp_path / "authorization.sqlite3"
    anchor = path.with_name(path.name + ".coordination.sqlite3")
    with pytest.raises(DurableAuthorizationStoreUnavailable, match="coordination paths"):
        DurableInvocationAuthorizationStore.initialize(path, anchor_path=anchor)
    assert list(tmp_path.iterdir()) == []


def test_coordination_failure_grants_no_claim(tmp_path):
    store = initialize_store(tmp_path / "authorization.sqlite3")
    persist(store)
    store._coordination_path.write_bytes(b"not a SQLite database")
    with pytest.raises(DurableAuthorizationStoreUnavailable):
        store.claim(authorization().to_canonical_dict(), consumed_at=NOW, validate=lambda: None)


def test_coordination_lock_timeout_fails_closed_and_then_recovers(tmp_path):
    store = initialize_store(tmp_path / "authorization.sqlite3")
    persist(store)
    connection = sqlite3.connect(str(store._coordination_path), isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(DurableAuthorizationStoreUnavailable, match="locked"):
            store.claim(authorization().to_canonical_dict(), consumed_at=NOW, validate=lambda: None)
    finally:
        connection.close()
    assert store.claim(authorization().to_canonical_dict(), consumed_at=NOW, validate=lambda: None).allowed
