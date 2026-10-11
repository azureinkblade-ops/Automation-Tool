"""Fake-only app boundary for explicit three-agent delegated result recovery."""

import inspect

import pytest

import app
from tests.hermes_core.test_ea4e92fu_agent_ping_delivery import ping_store
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError


def test_app_result_host_has_no_implicit_startup_or_route(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_AGENT_PING_RECOVERY_HOST", None)
    with pytest.raises(DelegationIntegrityError, match="not configured"):
        app.recover_governed_agent_ping("attempt-1")
    with pytest.raises(DelegationIntegrityError, match="not configured"):
        app.inspect_governed_agent_ping("attempt-1")
    assert "configure_governed_agent_ping_recovery" not in inspect.getsource(app.main)
    assert "recover_governed_agent_ping" not in inspect.getsource(app.main)
    assert "inspect_governed_agent_ping" not in inspect.getsource(app.main)


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_app_result_host_requires_explicit_enablement_and_replays_once(
    tmp_path, monkeypatch, agent,
):
    monkeypatch.setattr(app, "_GOVERNED_AGENT_PING_RECOVERY_HOST", None)
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
        app.configure_governed_agent_ping_recovery(
            authority, start, captures, registry, results,
        )
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            app.recover_governed_agent_ping(lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            app.inspect_governed_agent_ping(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
        app.configure_governed_agent_ping_recovery(
            authority, start, captures, registry, results, enabled=True,
        )
        assert app.inspect_governed_agent_ping(lease.attempt_id) == "TERMINAL_EVIDENCE_AVAILABLE"
        first = app.recover_governed_agent_ping(lease.attempt_id)
        assert first[0].outcome == "SUCCEEDED"
        assert app.inspect_governed_agent_ping(lease.attempt_id) == "MESSAGE_AVAILABLE"
        assert app.recover_governed_agent_ping(lease.attempt_id) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()
