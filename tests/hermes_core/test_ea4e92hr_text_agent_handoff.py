"""Fake-only accepted Kilo/OpenCode handoff through durable return."""

import pytest

from tests.hermes_core.durable_auth_test_support import qualification_store
from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hj_agent_delegated_claim_owner import owner
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_ping_return import return_bound_agent_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_accepted_text_agent_handoff_returns_one_originator_message(tmp_path, agent):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        resolution = fake_resolution(agent)
        bridge = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge.reserve(lease.attempt_id, resolution)
        intent = SQLiteAgentTextProcessIntentStore(bridge, clock=lambda: NOW)
        intent.reserve(lease.attempt_id, ["inert-receiver", "ping"])
        auth_store = qualification_store(tmp_path)
        claim_owner = owner(authority, start, auth_store)
        authorization = claim_owner.issue(
            lease.attempt_id, resolution,
        ).authorization
        claim = claim_owner.claim_and_fence(
            lease.attempt_id, resolution, authorization,
        )
        assert claim.status == "FENCED"
        assert auth_store.consumed_count() == 1
        assert intent.get(lease.attempt_id) is not None

        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        results = ping_store(authority.path)
        with pytest.raises(DelegationIntegrityError, match="terminal capture is absent"):
            return_bound_agent_ping(
                authority, start, capture_store(authority, start),
                registry, results, lease.attempt_id,
            )
        assert authority.list_mailbox(task.originator_agent_id) == []

        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        capture_store(authority, start).capture(
            lease.attempt_id, terminal_outcome(witness),
        )
        start.close()
        start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
        captures = capture_store(authority, start)
        first = return_bound_agent_ping(
            authority, start, captures, registry, results, lease.attempt_id,
        )
        second = return_bound_agent_ping(
            authority, start, captures, registry, results, lease.attempt_id,
        )
        assert second == first
        assert first[0].outcome == "SUCCEEDED"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()
