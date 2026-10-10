"""Fake-only Codex terminal ping return and originator replay."""

from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tools.hermes_core.agent_ping_return import return_codex_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def clock(at):
    return lambda: datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc,
    ).timestamp()


def ready(tmp_path, *, at="2026-08-27T12:05:04Z"):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    registry = durable_codex_record(tmp_path, witness, clock=clock(at))
    return authority, start, task, lease, registry


def test_codex_ping_returns_once_after_restart(tmp_path):
    authority, start, task, lease, registry = ready(tmp_path)
    start.close()
    start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        authority = SQLiteDelegationStore(authority.path)
        registry = CodexInvocationRegistry(registry.path)
        first = return_codex_ping(
            authority, start, registry, ping_store(authority.path), lease.attempt_id,
        )
        assert first[0].outcome == "SUCCEEDED"
        assert first[0].completed_at == "2026-08-27T12:05:04Z"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        replay = return_codex_ping(
            authority, start, registry,
            ping_store(authority.path, at="2026-08-27T12:10:01Z"),
            lease.attempt_id,
        )
        assert replay == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


def test_missing_codex_terminal_result_does_not_send(tmp_path):
    authority, start, task, lease, _ = ready(tmp_path)
    try:
        registry = CodexInvocationRegistry(str(tmp_path / "empty.sqlite3"))
        registry.initialize()
        results = ping_store(authority.path)
        with pytest.raises(DelegationIntegrityError):
            return_codex_ping(authority, start, registry, results, lease.attempt_id)
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


@pytest.mark.parametrize("case", ["cancelled", "delivery_expired", "terminal_early", "terminal_late"])
def test_codex_new_success_denied_when_authority_or_terminal_time_invalid(tmp_path, case):
    at = "2026-08-27T12:04:59Z" if case == "terminal_early" else (
        "2026-08-27T12:10:01Z" if case == "terminal_late" else "2026-08-27T12:05:04Z"
    )
    authority, start, task, lease, registry = ready(tmp_path, at=at)
    try:
        if case == "cancelled":
            authority.cancel_delegation(
                task.delegation_id, reason="operator cancellation",
                cancelled_at="2026-08-27T12:05:04Z",
            )
        results = ping_store(
            authority.path,
            at="2026-08-27T12:10:01Z" if case == "delivery_expired" else "2026-08-27T12:05:05Z",
        )
        with pytest.raises(DelegationIntegrityError):
            return_codex_ping(authority, start, registry, results, lease.attempt_id)
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_codex_existing_result_replays_after_cancellation(tmp_path):
    authority, start, task, lease, registry = ready(tmp_path)
    try:
        first = return_codex_ping(
            authority, start, registry, ping_store(authority.path), lease.attempt_id,
        )
        authority.cancel_delegation(
            task.delegation_id, reason="later cancellation",
            cancelled_at="2026-08-27T12:05:06Z",
        )
        replay = return_codex_ping(
            authority, start, registry,
            ping_store(authority.path, at="2026-08-27T12:10:01Z"),
            lease.attempt_id,
        )
        assert replay == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()
