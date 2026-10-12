"""Fake-only durable planning; no receiver or model is invoked."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_intent_binds_accepted_lineage_and_denies_second_reservation(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        bridge_store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge = bridge_store.reserve(lease.attempt_id, fake_resolution(agent))
        intent_store = SQLiteAgentTextProcessIntentStore(bridge_store, clock=lambda: NOW)
        first = intent_store.reserve(lease.attempt_id, ["inert-receiver", "--task", "ping"])
        assert first.attempt_id == lease.attempt_id
        assert first.receiver_agent_id == agent
        assert first.bridge_hash == bridge.artifact_hash
        assert first == SQLiteAgentTextProcessIntentStore(
            bridge_store, clock=lambda: NOW,
        ).get(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="already reserved"):
            intent_store.reserve(lease.attempt_id, ["inert-receiver", "--task", "ping"])
        with pytest.raises(DelegationIntegrityError, match="already reserved"):
            intent_store.reserve(lease.attempt_id, ["different-receiver"])
        assert authority.get_delegation(task.delegation_id) == task
    finally:
        start.close()


def test_intent_denies_cancelled_authority(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, task, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        bridge_store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge_store.reserve(lease.attempt_id, fake_resolution(agent))
        intent_store = SQLiteAgentTextProcessIntentStore(bridge_store, clock=lambda: NOW)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError):
            intent_store.reserve(lease.attempt_id, ["inert-receiver"])
        assert intent_store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_intent_denies_already_claimed_receiver_start(tmp_path):
    agent = "kilo-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        bridge_store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge_store.reserve(lease.attempt_id, fake_resolution(agent))
        intent_store = SQLiteAgentTextProcessIntentStore(bridge_store, clock=lambda: NOW)
        fence(authority, start).claim(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="receiver start already claimed"):
            intent_store.reserve(lease.attempt_id, ["inert-receiver"])
        assert intent_store.get(lease.attempt_id) is None
    finally:
        start.close()


def test_intent_rejects_bad_argv_and_tampered_row(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        bridge_store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge_store.reserve(lease.attempt_id, fake_resolution(agent))
        intent_store = SQLiteAgentTextProcessIntentStore(bridge_store, clock=lambda: NOW)
        for argv in ([], [""], ["inert\x00bad"], ["x" * 65537]):
            with pytest.raises(DelegationIntegrityError, match="command denied"):
                intent_store.reserve(lease.attempt_id, argv)
        intent_store.reserve(lease.attempt_id, ["inert-receiver"])
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_text_process_intents SET canonical_payload='{}' "
                "WHERE attempt_id=?", (lease.attempt_id,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            intent_store.get(lease.attempt_id)
    finally:
        start.close()


def test_independent_intent_writers_reserve_only_once(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(tmp_path, agent, ping=True)
    try:
        bridge_store = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge_store.reserve(lease.attempt_id, fake_resolution(agent))
        gate = Barrier(2)

        def reserve_once():
            separate_authority = SQLiteDelegationStore(tmp_path / "authority.sqlite3")
            separate_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
            try:
                separate_bridge = SQLiteAgentInvocationBridgeStore(
                    separate_authority, separate_start, clock=lambda: NOW,
                )
                intent_store = SQLiteAgentTextProcessIntentStore(
                    separate_bridge, clock=lambda: NOW,
                )
                gate.wait(timeout=5)
                try:
                    intent_store.reserve(lease.attempt_id, ["inert-receiver"])
                    return "RESERVED"
                except DelegationIntegrityError as exc:
                    assert "already reserved" in str(exc)
                    return "DENIED"
            finally:
                separate_start.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: reserve_once(), range(2)))
        assert sorted(outcomes) == ["DENIED", "RESERVED"]
        with sqlite3.connect(authority.path) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM agent_text_process_intents WHERE attempt_id=?",
                (lease.attempt_id,),
            ).fetchone() == (1,)
    finally:
        start.close()
