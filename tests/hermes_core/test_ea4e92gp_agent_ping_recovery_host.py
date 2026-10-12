"""Fake-only explicit host gate for delegated ping recovery."""

from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tools.hermes_core.agent_ping_recovery_host import AgentPingRecoveryHost
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def receiver_fence(authority, start):
    return SQLiteAgentReceiverStartFenceStore(
        authority, start,
        clock=lambda: datetime(2026, 8, 27, 12, 5, 4, tzinfo=timezone.utc),
    )


def stores(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    results = ping_store(authority.path)
    return authority, start, task, lease, capture_store(authority, start), registry, results


def test_recovery_host_is_disabled_by_default_and_has_no_side_effect(tmp_path):
    authority, start, task, lease, captures, registry, results = stores(tmp_path)
    try:
        host = AgentPingRecoveryHost(authority, start, captures, registry, results)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            host.recover(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            host.inspect(lease.attempt_id)
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_explicit_host_recovery_replays_one_codex_result(tmp_path):
    authority, start, task, lease, captures, _, results = stores(tmp_path)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        registry = durable_codex_record(
            tmp_path, witness, clock=clock("2026-08-27T12:05:04Z"),
        )
        host = AgentPingRecoveryHost(
            authority, start, captures, registry, results, enabled=True,
        )
        first = host.recover(lease.attempt_id)
        assert first[0].outcome == "SUCCEEDED"
        assert host.recover(lease.attempt_id) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_one_host_recovers_each_agent_after_store_reopen(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        captures = capture_store(authority, start)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        if agent == "codex-cli-agent":
            registry = durable_codex_record(
                tmp_path, witness, clock=clock("2026-08-27T12:05:04Z"),
            )
        else:
            captures.capture(lease.attempt_id, terminal_outcome(witness))
        start.close()
        start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        host = AgentPingRecoveryHost(
            authority, start, capture_store(authority, start), registry,
            ping_store(authority.path), enabled=True,
        )
        first = host.recover(lease.attempt_id)
        assert first[0].outcome == "SUCCEEDED"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        assert host.recover(lease.attempt_id) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


def test_recovery_host_rejects_nonexplicit_enablement_and_bad_attempt(tmp_path):
    authority, start, _, _, captures, registry, results = stores(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError, match="gate invalid"):
            AgentPingRecoveryHost(
                authority, start, captures, registry, results, enabled="yes",
            )
        host = AgentPingRecoveryHost(
            authority, start, captures, registry, results, enabled=True,
        )
        with pytest.raises(DelegationIntegrityError, match="attempt identity missing"):
            host.recover("")
        with pytest.raises(DelegationIntegrityError, match="attempt identity missing"):
            host.inspect("")
    finally:
        start.close()


def test_recovery_host_rejects_missing_or_mismatched_stores_at_configuration(tmp_path):
    authority, start, _, _, captures, registry, results = stores(tmp_path)
    other_start = SQLiteExecutionStartStore(tmp_path / "other-start.sqlite3")
    try:
        for dependencies in (
            (None, start, captures, registry, results),
            (authority, start, None, registry, results),
            (authority, other_start, captures, registry, results),
            (authority, start, captures, registry, None),
        ):
            with pytest.raises(DelegationIntegrityError, match="stores are not bound"):
                AgentPingRecoveryHost(*dependencies, enabled=True)
    finally:
        other_start.close()
        start.close()


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_inspect_is_read_only_across_terminal_and_delivery_states(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        captures = capture_store(authority, start)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        results = ping_store(authority.path)
        host = AgentPingRecoveryHost(
            authority, start, captures, registry, results, enabled=True,
        )
        assert host.inspect(lease.attempt_id) == "NO_TERMINAL_EVIDENCE"
        assert authority.list_mailbox(task.originator_agent_id) == []
        if agent == "codex-cli-agent":
            registry = durable_codex_record(
                tmp_path, witness, clock=clock("2026-08-27T12:05:04Z"),
            )
            host = AgentPingRecoveryHost(
                authority, start, captures, registry, results, enabled=True,
            )
        else:
            captures.capture(lease.attempt_id, terminal_outcome(witness))
        assert host.inspect(lease.attempt_id) == "TERMINAL_EVIDENCE_AVAILABLE"
        assert authority.list_mailbox(task.originator_agent_id) == []
        host.recover(lease.attempt_id)
        assert host.inspect(lease.attempt_id) == "MESSAGE_AVAILABLE"
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_inspect_claimed_receiver_without_terminal_is_unknown(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        captures = capture_store(authority, start)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        results = ping_store(authority.path)
        fence = receiver_fence(authority, start)
        host = AgentPingRecoveryHost(
            authority, start, captures, registry, results,
            enabled=True, receiver_starts=fence,
        )
        assert host.inspect(lease.attempt_id) == "NO_TERMINAL_EVIDENCE"
        fence.claim(lease.attempt_id)
        assert host.inspect(lease.attempt_id) == "RECEIVER_START_UNKNOWN"
        assert authority.list_mailbox(task.originator_agent_id) == []
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        captures.capture(lease.attempt_id, terminal_outcome(witness))
        assert host.inspect(lease.attempt_id) == "TERMINAL_EVIDENCE_AVAILABLE"
    finally:
        start.close()


def test_inspect_rejects_mismatched_receiver_start_fence(tmp_path):
    authority, start, _, _, captures, registry, results = stores(tmp_path)
    other_start = SQLiteExecutionStartStore(tmp_path / "other-start.sqlite3")
    try:
        with pytest.raises(DelegationIntegrityError, match="fence is not bound"):
            AgentPingRecoveryHost(
                authority, start, captures, registry, results,
                enabled=True, receiver_starts=receiver_fence(authority, other_start),
            )
    finally:
        other_start.close()
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_inspect_preserves_claim_ambiguity_after_authority_ends(
    tmp_path, agent, action,
):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        captures = capture_store(authority, start)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        fence = receiver_fence(authority, start)
        host = AgentPingRecoveryHost(
            authority, start, captures, registry, ping_store(authority.path),
            enabled=True, receiver_starts=fence,
        )
        fence.claim(lease.attempt_id)
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
        assert host.inspect(lease.attempt_id) == "RECEIVER_START_UNKNOWN"
        with pytest.raises(DelegationIntegrityError):
            fence.claim(lease.attempt_id)
    finally:
        start.close()
