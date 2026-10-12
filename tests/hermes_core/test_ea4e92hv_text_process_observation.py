"""Fake-reported process events; no executable or model starts."""

import sqlite3

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hj_agent_delegated_claim_owner import owner
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.agent_text_process_observation import (
    SQLiteAgentTextProcessObservationStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


ARGV = ("inert-receiver", "ping")


def prepared(tmp_path, agent, *, claimed=True):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    resolution = fake_resolution(agent)
    bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
    bridges.reserve(lease.attempt_id, resolution)
    intents = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
    intents.reserve(lease.attempt_id, ARGV)
    fences = SQLiteAgentReceiverStartFenceStore(authority, start, clock=lambda: NOW)
    if claimed:
        auth_store = qualification_store(tmp_path)
        current_owner = owner(authority, start, auth_store)
        authorization = current_owner.issue(lease.attempt_id, resolution).authorization
        assert current_owner.claim_and_fence(
            lease.attempt_id, resolution, authorization,
        ).status == "FENCED"
    observations = SQLiteAgentTextProcessObservationStore(
        intents, fences, clock=lambda: NOW,
    )
    return authority, start, task, lease, observations


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_reported_start_and_raw_terminal_survive_reopen(tmp_path, agent):
    authority, start, _, lease, observations = prepared(tmp_path, agent)
    try:
        reported = observations.record_start(
            lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234,
        )
        assert reported.intent_hash == observations.intents.get(lease.attempt_id).payload_sha256
        assert reported.fence_hash == observations.fences.get(lease.attempt_id).claim_hash
        assert observations.get_terminal(lease.attempt_id) is None
        terminal = observations.record_terminal(
            lease.attempt_id, owner_id="fake-owner-1", pid=1234,
            returncode=0, stdout_bytes=b'{"type":"text","text":"PONG"}\n',
            stderr_bytes=b"",
        )
        assert terminal.start_hash == reported.start_hash
        assert terminal.stdout_bytes == b'{"type":"text","text":"PONG"}\n'
        reopened = SQLiteAgentTextProcessObservationStore(
            observations.intents, observations.fences, clock=lambda: NOW,
        )
        assert reopened.get_start(lease.attempt_id) == reported
        assert reopened.get_terminal(lease.attempt_id) == terminal
        assert reopened.record_terminal(
            lease.attempt_id, owner_id="fake-owner-1", pid=1234,
            returncode=0, stdout_bytes=terminal.stdout_bytes,
            stderr_bytes=b"",
        ) == terminal
        with pytest.raises(DelegationIntegrityError, match="already recorded"):
            reopened.record_start(lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234)
        with pytest.raises(DelegationIntegrityError, match="divergent"):
            reopened.record_terminal(
                lease.attempt_id, owner_id="fake-owner-1", pid=1234,
                returncode=1, stdout_bytes=terminal.stdout_bytes,
                stderr_bytes=b"",
            )
    finally:
        start.close()


def test_start_requires_fence_and_exact_reserved_command(tmp_path):
    authority, start, _, lease, observations = prepared(
        tmp_path, "kilo-cli-agent", claimed=False,
    )
    try:
        with pytest.raises(DelegationIntegrityError, match="fence mismatch"):
            observations.record_start(
                lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234,
            )
        with pytest.raises(DelegationIntegrityError, match="command or bridge mismatch"):
            observations.record_start(
                lease.attempt_id, ("different",), owner_id="fake-owner-1", pid=1234,
            )
        assert observations.get_start(lease.attempt_id) is None
    finally:
        start.close()


def test_direct_fence_without_authorization_claim_cannot_report_start(tmp_path):
    authority, start, _, lease, observations = prepared(
        tmp_path, "kilo-cli-agent", claimed=False,
    )
    try:
        observations.fences.claim(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="authority changed"):
            observations.record_start(
                lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234,
            )
        assert observations.get_start(lease.attempt_id) is None
    finally:
        start.close()


def test_terminal_accounting_survives_cancellation_but_not_owner_change(tmp_path):
    authority, start, task, lease, observations = prepared(
        tmp_path, "opencode-cli-agent",
    )
    try:
        observations.record_start(lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234)
        authority.cancel_delegation(
            task.delegation_id, reason="operator", cancelled_at="2026-08-27T12:05:04Z",
        )
        with pytest.raises(DelegationIntegrityError, match="owner mismatch"):
            observations.record_terminal(
                lease.attempt_id, owner_id="other-owner", pid=1234,
                returncode=1, stdout_bytes=b"", stderr_bytes=b"cancelled",
            )
        terminal = observations.record_terminal(
            lease.attempt_id, owner_id="fake-owner-1", pid=1234,
            returncode=1, stdout_bytes=b"", stderr_bytes=b"cancelled",
        )
        assert terminal.stderr_bytes == b"cancelled"
        assert observations.get_terminal(lease.attempt_id) == terminal
    finally:
        start.close()


def test_terminal_bytes_and_start_checksum_tamper_fail_closed(tmp_path):
    authority, start, _, lease, observations = prepared(
        tmp_path, "kilo-cli-agent",
    )
    try:
        observations.record_start(lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234)
        observations.record_terminal(
            lease.attempt_id, owner_id="fake-owner-1", pid=1234,
            returncode=0, stdout_bytes=b"PONG", stderr_bytes=b"",
        )
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_text_process_terminals SET stdout_bytes=? WHERE attempt_id=?",
                (b"EVIL", lease.attempt_id),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            observations.get_terminal(lease.attempt_id)
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_text_process_starts SET canonical_payload='{}' WHERE attempt_id=?",
                (lease.attempt_id,),
            )
        with pytest.raises(DelegationIntegrityError, match="integrity mismatch"):
            observations.get_start(lease.attempt_id)
    finally:
        start.close()


def test_terminal_is_bounded_and_requires_reported_start(tmp_path):
    authority, start, _, lease, observations = prepared(
        tmp_path, "kilo-cli-agent",
    )
    try:
        with pytest.raises(DelegationIntegrityError, match="owner mismatch"):
            observations.record_terminal(
                lease.attempt_id, owner_id="fake-owner-1", pid=1234,
                returncode=0, stdout_bytes=b"PONG", stderr_bytes=b"",
            )
        observations.record_start(lease.attempt_id, ARGV, owner_id="fake-owner-1", pid=1234)
        with pytest.raises(DelegationIntegrityError, match="data denied"):
            observations.record_terminal(
                lease.attempt_id, owner_id="fake-owner-1", pid=1234,
                returncode=0, stdout_bytes=b"x" * (4 * 1024 * 1024 + 1),
                stderr_bytes=b"",
            )
        assert observations.get_terminal(lease.attempt_id) is None
    finally:
        start.close()
