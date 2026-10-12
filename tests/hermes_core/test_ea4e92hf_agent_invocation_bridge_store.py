"""Fake-only durable reservation of delegated invocation identity."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def bridge_store(authority, start):
    return SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_reservation_replays_exactly_after_reopen(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = bridge_store(authority, start)
        resolution = fake_resolution(agent)
        first = store.reserve(lease.attempt_id, resolution)
        assert first.verify_hash()
        assert bridge_store(authority, start).get(lease.attempt_id) == first
        assert bridge_store(authority, start).reserve(lease.attempt_id, resolution) == first
        with sqlite3.connect(authority.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM agent_invocation_bridges").fetchone() == (1,)
    finally:
        start.close()


def test_divergent_binding_replay_denied(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = bridge_store(authority, start)
        first = store.reserve(lease.attempt_id, fake_resolution(agent))
        with pytest.raises(DelegationIntegrityError, match="divergent"):
            store.reserve(lease.attempt_id, fake_resolution(agent, binding_id="other-binding"))
        assert store.get(lease.attempt_id) == first
    finally:
        start.close()


@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_reservation_cannot_be_reused_after_authority_ends(tmp_path, action):
    agent = "opencode-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = bridge_store(authority, start)
        first = store.reserve(lease.attempt_id, fake_resolution(agent))
        if action == "cancel":
            authority.cancel_delegation(
                task.delegation_id, reason="operator",
                cancelled_at="2026-08-27T12:05:05Z",
            )
        else:
            authority.revoke_lease(
                lease.lease_id, reason="operator",
                revoked_at="2026-08-27T12:05:05Z",
            )
        assert store.get(lease.attempt_id) == first
        with pytest.raises(DelegationIntegrityError):
            store.reserve(lease.attempt_id, fake_resolution(agent))
    finally:
        start.close()


def test_reservation_denies_claimed_receiver_start(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        fence(authority, start).claim(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="already claimed"):
            bridge_store(authority, start).reserve(lease.attempt_id, fake_resolution(agent))
    finally:
        start.close()


def test_cancelled_attempt_cannot_reserve_for_first_time(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = bridge_store(authority, start)
        authority.cancel_delegation(
            task.delegation_id, reason="operator",
            cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError):
            store.reserve(lease.attempt_id, fake_resolution(agent))
        assert store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_terminal_capture_denies_late_first_reservation(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        capture_store(authority, start).capture(
            lease.attempt_id, terminal_outcome(witness),
        )
        with pytest.raises(DelegationIntegrityError, match="terminal state"):
            bridge_store(authority, start).reserve(
                lease.attempt_id, fake_resolution(agent),
            )
    finally:
        start.close()


def test_corrupt_persisted_reservation_denies_read_and_replay(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        store = bridge_store(authority, start)
        store.reserve(lease.attempt_id, fake_resolution(agent))
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_invocation_bridges SET payload_sha256=? WHERE attempt_id=?",
                ("0" * 64, lease.attempt_id),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity"):
            store.get(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="integrity"):
            store.reserve(lease.attempt_id, fake_resolution(agent))
    finally:
        start.close()


def test_concurrent_same_identity_reserves_one_row(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        resolution = fake_resolution(agent)
        def reserve():
            independent_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
            try:
                return bridge_store(authority, independent_start).reserve(
                    lease.attempt_id, resolution,
                )
            finally:
                independent_start.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: reserve(), range(2)))
        assert first == second
        with sqlite3.connect(authority.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM agent_invocation_bridges").fetchone() == (1,)
    finally:
        start.close()
