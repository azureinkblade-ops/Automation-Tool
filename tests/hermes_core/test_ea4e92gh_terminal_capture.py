"""Fake-only Kilo/OpenCode terminal capture and restart recovery."""

import sqlite3
from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tools.hermes_core.agent_ping_result import build_validated_agent_ping_result
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_capture_reopens_identical_candidate_without_new_send(tmp_path, agent):
    authority, start, task, lease, receipt, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        outcome = terminal_outcome(witness)
        store = SQLiteAgentTerminalCaptureStore(authority, start)
        first = store.capture(lease.attempt_id, outcome)
        assert store.capture(lease.attempt_id, outcome) == first
        start.close()
        start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        reopened = SQLiteAgentTerminalCaptureStore(authority, start)
        recovered = reopened.get(lease.attempt_id)
        assert recovered == first
        result = build_validated_agent_ping_result(
            task, lease, receipt, recovered.candidate,
            started_at=witness.start_result.recorded_at,
            completed_at="2026-08-27T12:05:04Z",
        )
        assert result.outcome == "SUCCEEDED"
        assert result.output_manifest == ()
        with sqlite3.connect(authority.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM agent_terminal_captures").fetchone()[0] == 1
    finally:
        start.close()


def test_missing_capture_after_restart_remains_unknown(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        assert SQLiteAgentTerminalCaptureStore(authority, start).get(lease.attempt_id) is None
    finally:
        start.close()


@pytest.mark.parametrize("forgery", ["send", "text", "terminal"])
def test_divergent_or_invalid_capture_cannot_replace_original(tmp_path, forgery):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        store = SQLiteAgentTerminalCaptureStore(authority, start)
        original = store.capture(lease.attempt_id, terminal_outcome(witness))
        outcome = terminal_outcome(witness)
        if forgery == "send":
            outcome = replace(outcome, record=replace(outcome.record, idempotency_key="other"))
        elif forgery == "terminal":
            outcome = replace(outcome, record=replace(outcome.record, terminal_state="error"))
        else:
            payload = dict(outcome.verified_result.payload)
            payload["text"] = payload["text"].replace("PING_OK", "PING_BAD")
            outcome = replace(outcome, verified_result=replace(
                outcome.verified_result, payload=payload,
            ))
        with pytest.raises(DelegationIntegrityError):
            store.capture(lease.attempt_id, outcome)
        assert store.get(lease.attempt_id) == original
    finally:
        start.close()


def test_corrupt_persisted_capture_denied_after_restart(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        store = SQLiteAgentTerminalCaptureStore(authority, start)
        store.capture(lease.attempt_id, terminal_outcome(witness))
        with sqlite3.connect(authority.path) as conn:
            conn.execute(
                "UPDATE agent_terminal_captures SET canonical_payload='{}' WHERE attempt_id=?",
                (lease.attempt_id,),
            )
        with pytest.raises(DelegationIntegrityError):
            store.get(lease.attempt_id)
    finally:
        start.close()


def test_cancelled_delegation_cannot_recover_terminal_capture(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        store = SQLiteAgentTerminalCaptureStore(authority, start)
        store.capture(lease.attempt_id, terminal_outcome(witness))
        authority.cancel_delegation(
            task.delegation_id, reason="operator cancellation",
            cancelled_at="2026-08-27T12:05:03Z",
        )
        with pytest.raises(DelegationIntegrityError):
            store.get(lease.attempt_id)
    finally:
        start.close()
