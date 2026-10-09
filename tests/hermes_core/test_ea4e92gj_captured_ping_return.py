"""Fake-only captured text ping return and originator recovery."""

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tools.hermes_core.agent_ping_return import return_captured_text_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_capture_returns_one_result_and_mailbox_message_after_restart(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    capture_store(authority, start).capture(lease.attempt_id, terminal_outcome(witness))
    start.close()
    start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        authority = SQLiteDelegationStore(authority.path)
        captures = capture_store(authority, start, at="2026-08-27T12:10:01Z")
        results = ping_store(authority.path)
        first = return_captured_text_ping(authority, captures, results, lease.attempt_id)
        assert first[0].outcome == "SUCCEEDED"
        assert first[0].completed_at == "2026-08-27T12:05:04Z"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        replay = return_captured_text_ping(
            authority, captures, ping_store(authority.path, at="2026-08-27T12:10:01Z"),
            lease.attempt_id,
        )
        assert replay == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


def test_missing_capture_does_not_complete_or_send(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        results = ping_store(authority.path)
        with pytest.raises(DelegationIntegrityError):
            return_captured_text_ping(
                authority, capture_store(authority, start), results, lease.attempt_id,
            )
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_cancel_after_capture_denies_new_success(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        captures = capture_store(authority, start)
        captures.capture(lease.attempt_id, terminal_outcome(witness))
        authority.cancel_delegation(
            task.delegation_id, reason="operator cancellation",
            cancelled_at="2026-08-27T12:05:04Z",
        )
        results = ping_store(authority.path)
        with pytest.raises(DelegationIntegrityError):
            return_captured_text_ping(authority, captures, results, lease.attempt_id)
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
    finally:
        start.close()


def test_existing_result_replays_after_later_cancellation(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        captures = capture_store(authority, start)
        captures.capture(lease.attempt_id, terminal_outcome(witness))
        first = return_captured_text_ping(
            authority, captures, ping_store(authority.path), lease.attempt_id,
        )
        authority.cancel_delegation(
            task.delegation_id, reason="later cancellation",
            cancelled_at="2026-08-27T12:05:06Z",
        )
        replay = return_captured_text_ping(
            authority, captures, ping_store(authority.path, at="2026-08-27T12:10:01Z"),
            lease.attempt_id,
        )
        assert replay == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()
