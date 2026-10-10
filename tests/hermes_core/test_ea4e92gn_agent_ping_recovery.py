"""Store-only recovery entrypoint for all three delegated ping receivers."""

import pytest

from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tools.hermes_core.agent_ping_return import return_bound_agent_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_three_agents_return_once_through_store_only_entrypoint(tmp_path, agent):
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
        results = ping_store(authority.path)
        first = return_bound_agent_ping(
            authority, start, captures, registry, results, lease.attempt_id,
        )
        assert first[0].outcome == "SUCCEEDED"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        replay = return_bound_agent_ping(
            authority, start, captures, registry, results, lease.attempt_id,
        )
        assert replay == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


def test_recovery_rejects_unbound_start_store(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    other_authority, other_start, _, _, _, _ = stores_and_artifacts(
        tmp_path / "other", "kilo-cli-agent", ping=True,
    )
    try:
        captures = capture_store(other_authority, other_start)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        with pytest.raises(DelegationIntegrityError, match="not bound"):
            return_bound_agent_ping(
                authority, start, captures, registry,
                ping_store(authority.path), lease.attempt_id,
            )
    finally:
        start.close()
        other_start.close()
