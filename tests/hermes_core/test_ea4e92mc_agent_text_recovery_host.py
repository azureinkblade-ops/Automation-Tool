"""Fake-only default-disabled recovery of bounded agent text."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tests.hermes_core.test_ea4e92lw_agent_text_result import DELIVERY_TIME
from tests.hermes_core.test_ea4e92lx_agent_text_return import body_for
from tests.hermes_core.test_ea4e92ly_agent_text_response_command import ready as ready_process
from tests.hermes_core.test_ea4e92ma_codex_text_question import ready as ready_codex
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_text_recovery_host import AgentTextRecoveryHost
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def host(authority, start, registry, *, enabled=True):
    captures = capture_store(authority, start)
    results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
    return AgentTextRecoveryHost(
        authority, start, captures, registry, results, enabled=enabled,
    ), results


def test_disabled_host_does_not_deliver(tmp_path):
    authority, start, task, lease, _, _ = ready_codex(tmp_path)
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    try:
        subject, results = host(authority, start, registry, enabled=False)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            subject.inspect(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            subject.recover(lease.attempt_id)
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_host_inspect_then_recover_after_store_reopen(tmp_path, agent):
    if agent == "codex-cli-agent":
        authority, start, task, lease, _, _ = ready_codex(tmp_path)
        attempt_id = lease.attempt_id
    else:
        start, task, receipt, bridges, _, witness, _ = ready_process(tmp_path, agent)
        authority = bridges.authority
        attempt_id = witness.lease.attempt_id
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    try:
        subject, _ = host(authority, start, registry)
        assert subject.inspect(attempt_id) == "NO_TERMINAL_EVIDENCE"
        witness = load_bound_agent_start(authority, start, attempt_id)
        body = body_for(witness, text="cedar")
        if agent == "codex-cli-agent":
            registry = durable_codex_record(
                tmp_path, witness, body=body,
                clock=clock("2026-08-27T12:05:04Z"),
            )
        else:
            outcome = terminal_outcome(witness)
            outcome = replace(
                outcome, verified_result=replace(
                    outcome.verified_result,
                    payload={"type": "text", "text": canonical_json(body)},
                ),
            )
            capture_store(authority, start).capture(attempt_id, outcome)
        start.close()
        start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        subject, _ = host(authority, start, registry)
        assert subject.inspect(attempt_id) == "TERMINAL_EVIDENCE_AVAILABLE"
        assert authority.list_mailbox(task.originator_agent_id) == []
        first = subject.recover(attempt_id)
        assert first[0].result_payload["text"] == "cedar"
        assert subject.inspect(attempt_id) == "MESSAGE_AVAILABLE"
        assert subject.recover(attempt_id) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


def test_host_rejects_unbound_stores_and_nonboolean_enablement(tmp_path):
    authority, start, _, _, _, _ = ready_codex(tmp_path)
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
    other_start = SQLiteExecutionStartStore(tmp_path / "other.sqlite3")
    try:
        with pytest.raises(DelegationIntegrityError, match="gate invalid"):
            AgentTextRecoveryHost(
                authority, start, capture_store(authority, start), registry,
                results, enabled="yes",
            )
        with pytest.raises(DelegationIntegrityError, match="stores are not bound"):
            AgentTextRecoveryHost(
                authority, other_start, capture_store(authority, start),
                registry, results, enabled=True,
            )
    finally:
        other_start.close()
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_claimed_start_without_terminal_is_unknown(tmp_path, agent):
    start, task, _, bridges, _, witness, _ = ready_process(tmp_path, agent)
    authority = bridges.authority
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    fence = SQLiteAgentReceiverStartFenceStore(
        authority, start,
        clock=lambda: datetime(2026, 8, 27, 12, 5, 4, tzinfo=timezone.utc),
    )
    results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
    try:
        subject = AgentTextRecoveryHost(
            authority, start, capture_store(authority, start), registry,
            results, enabled=True, receiver_starts=fence,
        )
        attempt_id = witness.lease.attempt_id
        assert subject.inspect(attempt_id) == "NO_TERMINAL_EVIDENCE"
        fence.claim(attempt_id)
        assert subject.inspect(attempt_id) == "RECEIVER_START_UNKNOWN"
        authority.cancel_delegation(
            task.delegation_id, reason="operator",
            cancelled_at="2026-08-27T12:05:05Z",
        )
        assert subject.inspect(attempt_id) == "RECEIVER_START_UNKNOWN"
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_host_rejects_ping_schema_and_invalid_attempt(tmp_path):
    from tests.hermes_core.test_ea4e92gp_agent_ping_recovery_host import stores

    authority, start, _, lease, captures, registry, results = stores(tmp_path)
    try:
        subject = AgentTextRecoveryHost(
            authority, start, captures, registry, results, enabled=True,
        )
        with pytest.raises(DelegationIntegrityError, match="schema or receiver"):
            subject.inspect(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError):
            subject.recover(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="identity missing"):
            subject.inspect("")
    finally:
        start.close()
