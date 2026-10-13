"""Durable Linux Kilo plan reservation, without Docker or receiver activity."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Barrier

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hc_agent_receiver_start_fence import fence
from tests.hermes_core.test_ea4e92hu_text_ping_command import PING_LEASE, PING_TASK
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_local_kilo_ping_intent import SQLiteAgentLocalKiloPingIntentStore
from tools.hermes_core.agent_local_kilo_ping_plan import build_agent_local_kilo_ping_plan
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def accepted(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
        task_changes=PING_TASK, lease_changes=PING_LEASE,
    )
    bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
    bridge = bridges.reserve(lease.attempt_id, fake_resolution("kilo-cli-agent"))
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    plan = build_agent_local_kilo_ping_plan(witness, bridge)
    return authority, start, task, lease, bridges, plan


def test_plan_reservation_is_durable_and_replay_denies(tmp_path):
    authority, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        saved = intents.reserve(lease.attempt_id, plan)
        reopened = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        assert reopened.get(lease.attempt_id) == saved
        assert reopened.verify_plan(lease.attempt_id, plan) == saved
        with pytest.raises(DelegationIntegrityError, match="already reserved"):
            reopened.reserve(lease.attempt_id, plan)
        assert saved.plan_hash == plan["plan_hash"]
    finally:
        start.close()


def test_mutated_plan_and_cancelled_authority_deny(tmp_path):
    authority, start, task, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        saved = intents.reserve(lease.attempt_id, plan)
        changed = deepcopy(plan)
        changed["image_manifest"] = "sha256:" + "0" * 64
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            intents.verify_plan(lease.attempt_id, changed)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError, match="inactive"):
            intents.verify_plan(lease.attempt_id, plan)
        assert intents.get(lease.attempt_id) == saved
    finally:
        start.close()


def test_windows_and_linux_intents_exclude_each_other(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        linux = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        windows = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
        linux.reserve(lease.attempt_id, plan)
        with pytest.raises(DelegationIntegrityError, match="Linux Kilo plan already reserved"):
            windows.reserve(lease.attempt_id, ["inert-receiver"])
    finally:
        start.close()

    _, start, _, lease, bridges, plan = accepted(tmp_path / "opposite")
    try:
        linux = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        windows = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
        windows.reserve(lease.attempt_id, ["inert-receiver"])
        with pytest.raises(DelegationIntegrityError, match="too late or conflicting"):
            linux.reserve(lease.attempt_id, plan)
    finally:
        start.close()


def test_tampered_row_denies(tmp_path):
    authority, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        intents.reserve(lease.attempt_id, plan)
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_local_kilo_ping_intents SET canonical_payload='{}' "
                "WHERE attempt_id=?", (lease.attempt_id,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            intents.get(lease.attempt_id)
    finally:
        start.close()


def test_reservation_after_start_fence_denies(tmp_path):
    authority, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
        fence(authority, start).claim(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="too late or conflicting"):
            intents.reserve(lease.attempt_id, plan)
        assert intents.get(lease.attempt_id) is None
    finally:
        start.close()


def test_reservation_at_lease_expiry_denies(tmp_path):
    _, start, _, lease, bridges, plan = accepted(tmp_path)
    try:
        witness = load_bound_agent_start(
            bridges.authority, start, lease.attempt_id,
        )
        expired = datetime.fromisoformat(witness.lease.expires_at.replace("Z", "+00:00"))
        intents = SQLiteAgentLocalKiloPingIntentStore(
            bridges, clock=lambda: expired,
        )
        with pytest.raises(DelegationIntegrityError, match="outside lease window"):
            intents.reserve(lease.attempt_id, plan)
        assert intents.get(lease.attempt_id) is None
    finally:
        start.close()


def test_independent_reservation_race_has_one_winner(tmp_path):
    _, start, _, lease, _, plan = accepted(tmp_path)
    try:
        gate = Barrier(2)

        def reserve_once():
            authority = SQLiteDelegationStore(tmp_path / "authority.sqlite3")
            own_start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
            try:
                bridges = SQLiteAgentInvocationBridgeStore(
                    authority, own_start, clock=lambda: NOW,
                )
                intents = SQLiteAgentLocalKiloPingIntentStore(bridges, clock=lambda: NOW)
                gate.wait(timeout=5)
                try:
                    intents.reserve(lease.attempt_id, plan)
                    return "RESERVED"
                except DelegationIntegrityError as exc:
                    assert "already reserved" in str(exc)
                    return "DENIED"
            finally:
                own_start.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: reserve_once(), range(2))) == [
                "DENIED", "RESERVED",
            ]
    finally:
        start.close()
