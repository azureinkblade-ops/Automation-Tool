"""Fake-only explicit host gate for delegated ping recovery."""

import pytest

from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tools.hermes_core.agent_ping_recovery_host import AgentPingRecoveryHost
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError


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
    finally:
        start.close()
