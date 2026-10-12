"""Fake-only, temporary-DB qualification for a delegated receiver start fence."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def fence(authority, start, at="2026-08-27T12:05:04Z"):
    instant = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return SQLiteAgentReceiverStartFenceStore(authority, start, clock=lambda: instant)


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_one_claim_survives_restart_and_second_start_denies(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        first = fence(authority, start)
        assert first.get(lease.attempt_id) is None
        claimed = first.claim(lease.attempt_id)
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        assert claimed.receiver_agent_id == agent
        assert claimed.receipt_hash == witness.receipt.artifact_hash
        assert claimed.launch_attempt_hash == witness.launch.artifact_hash
        assert claimed.start_result_hash == witness.start_result.artifact_hash
        assert claimed.idempotency_key == witness.bound.invocation.idempotency_key
        assert claimed.runtime_run_id == witness.bound.invocation.runtime_run_id
        assert claimed.claimed_at == "2026-08-27T12:05:04Z"
        with pytest.raises(DelegationIntegrityError, match="already claimed"):
            first.claim(lease.attempt_id)
        start.close()
        start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        reopened = fence(authority, start)
        assert reopened.get(lease.attempt_id) == claimed
        with pytest.raises(DelegationIntegrityError, match="already claimed"):
            reopened.claim(lease.attempt_id)
        with sqlite3.connect(authority.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM agent_receiver_start_fences").fetchone()[0] == 1
    finally:
        start.close()


@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_inactive_authority_cannot_claim(tmp_path, action):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    try:
        store = fence(authority, start)
        if action == "cancel":
            authority.cancel_delegation(
                task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:02Z",
            )
        else:
            authority.revoke_lease(
                lease.lease_id, reason="operator", revoked_at="2026-08-27T12:05:02Z",
            )
        with pytest.raises(DelegationIntegrityError):
            store.claim(lease.attempt_id)
        assert store.get(lease.attempt_id) is None
    finally:
        start.close()


@pytest.mark.parametrize("at", ["2026-08-27T12:04:59Z", "2026-08-27T12:10:00Z"])
def test_outside_start_or_lease_window_denied(tmp_path, at):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        store = fence(authority, start, at=at)
        with pytest.raises(DelegationIntegrityError, match="outside lease window"):
            store.claim(lease.attempt_id)
        assert store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_missing_start_and_unsupported_receiver_denied(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", persist_start=False, ping=True,
    )
    try:
        with pytest.raises(DelegationIntegrityError):
            fence(authority, start).claim(lease.attempt_id)
    finally:
        start.close()
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path / "codex", "codex-cli-agent", ping=True,
    )
    try:
        with pytest.raises(DelegationIntegrityError, match="text agents only"):
            fence(authority, start).claim(lease.attempt_id)
    finally:
        start.close()


def test_corrupt_claim_denied_after_restart(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        store = fence(authority, start)
        store.claim(lease.attempt_id)
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_receiver_start_fences SET canonical_payload='{}' WHERE attempt_id=?",
                (lease.attempt_id,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            fence(authority, start).get(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError):
            store.claim(lease.attempt_id)
    finally:
        start.close()


def test_two_independent_claimers_admit_only_one(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    start.close()
    barrier = Barrier(2)

    def attempt_claim():
        local_authority = SQLiteDelegationStore(authority.path)
        local_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        try:
            store = fence(local_authority, local_start)
            barrier.wait(timeout=5)
            try:
                return store.claim(lease.attempt_id)
            except DelegationIntegrityError as exc:
                return str(exc)
        finally:
            local_start.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt_claim(), range(2)))
    assert sum(not isinstance(outcome, str) for outcome in outcomes) == 1
    assert sum(outcome == "receiver start already claimed; reconcile only"
               for outcome in outcomes if isinstance(outcome, str)) == 1
    with sqlite3.connect(authority.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_receiver_start_fences").fetchone()[0] == 1


def test_claim_remains_visible_after_cancellation_but_cannot_be_reused(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        store = fence(authority, start)
        claimed = store.claim(lease.attempt_id)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:05Z",
        )
        assert store.get(lease.attempt_id) == claimed
        with pytest.raises(DelegationIntegrityError):
            store.claim(lease.attempt_id)
    finally:
        start.close()


def test_lease_expiry_is_checked_after_write_lock_is_acquired(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    start.close()
    ready = Event()
    proceed = Event()
    started = Event()
    clock_called = Event()
    current_time = ["2026-08-27T12:05:04Z"]

    def trusted_clock():
        clock_called.set()
        return datetime.strptime(current_time[0], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc,
        )

    def attempt_claim():
        local_authority = SQLiteDelegationStore(authority.path)
        local_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        try:
            store = SQLiteAgentReceiverStartFenceStore(
                local_authority, local_start, clock=trusted_clock,
            )
            ready.set()
            assert proceed.wait(timeout=5)
            started.set()
            with pytest.raises(DelegationIntegrityError, match="outside lease window"):
                store.claim(lease.attempt_id)
        finally:
            local_start.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(attempt_claim)
        assert ready.wait(timeout=5)
        with sqlite3.connect(authority.path) as lock:
            lock.execute("BEGIN IMMEDIATE")
            proceed.set()
            try:
                assert started.wait(timeout=5)
                assert not clock_called.wait(timeout=0.1)
            finally:
                current_time[0] = "2026-08-27T12:10:00Z"
                lock.commit()
        future.result(timeout=5)
    assert clock_called.is_set()
    with sqlite3.connect(authority.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_receiver_start_fences").fetchone()[0] == 0


def test_existing_terminal_capture_prevents_late_first_start_claim(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        capture_store(authority, start).capture(lease.attempt_id, terminal_outcome(witness))
        store = fence(authority, start)
        with pytest.raises(DelegationIntegrityError, match="terminal state already recorded"):
            store.claim(lease.attempt_id)
        assert store.get(lease.attempt_id) is None
    finally:
        start.close()
