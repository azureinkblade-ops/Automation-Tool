"""Fake-only app boundary for explicit bounded three-agent text recovery."""

from dataclasses import replace
from datetime import datetime, timezone
import inspect

import pytest

import app
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
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore


def test_text_recovery_requires_explicit_configuration(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_AGENT_TEXT_RECOVERY_HOST", None)
    with pytest.raises(DelegationIntegrityError, match="not configured"):
        app.inspect_governed_agent_text("attempt-1")
    with pytest.raises(DelegationIntegrityError, match="not configured"):
        app.recover_governed_agent_text("attempt-1")
    main_source = inspect.getsource(app.main)
    assert "configure_governed_agent_text_recovery" not in main_source
    assert "inspect_governed_agent_text" not in main_source
    assert "recover_governed_agent_text" not in main_source


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_explicit_app_text_recovery_is_disabled_then_idempotent(
    tmp_path, monkeypatch, agent,
):
    monkeypatch.setattr(app, "_GOVERNED_AGENT_TEXT_RECOVERY_HOST", None)
    if agent == "codex-cli-agent":
        authority, start, task, lease, _, _ = ready_codex(tmp_path)
        attempt_id = lease.attempt_id
    else:
        start, task, _, bridges, _, witness, _ = ready_process(tmp_path, agent)
        authority = bridges.authority
        attempt_id = witness.lease.attempt_id
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    try:
        captures = capture_store(authority, start)
        results = SQLiteDelegationResultStore(
            authority.path, clock=lambda: DELIVERY_TIME,
        )
        app.configure_governed_agent_text_recovery(
            authority, start, captures, registry, results,
        )
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            app.inspect_governed_agent_text(attempt_id)
        with pytest.raises(DelegationIntegrityError, match="disabled"):
            app.recover_governed_agent_text(attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []

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
            captures.capture(attempt_id, outcome)
        app.configure_governed_agent_text_recovery(
            authority, start, captures, registry, results, enabled=True,
        )
        assert app.inspect_governed_agent_text(attempt_id) == "TERMINAL_EVIDENCE_AVAILABLE"
        first = app.recover_governed_agent_text(attempt_id)
        assert first[0].result_payload["text"] == "cedar"
        assert app.inspect_governed_agent_text(attempt_id) == "MESSAGE_AVAILABLE"
        assert app.recover_governed_agent_text(attempt_id) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_claimed_receiver_without_text_remains_unknown(tmp_path, monkeypatch, agent):
    monkeypatch.setattr(app, "_GOVERNED_AGENT_TEXT_RECOVERY_HOST", None)
    start, task, _, bridges, _, witness, _ = ready_process(tmp_path, agent)
    authority = bridges.authority
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    try:
        captures = capture_store(authority, start)
        results = SQLiteDelegationResultStore(
            authority.path, clock=lambda: DELIVERY_TIME,
        )
        fence = SQLiteAgentReceiverStartFenceStore(
            authority, start,
            clock=lambda: datetime(2026, 8, 27, 12, 5, 4, tzinfo=timezone.utc),
        )
        app.configure_governed_agent_text_recovery(
            authority, start, captures, registry, results,
            enabled=True, receiver_starts=fence,
        )
        fence.claim(witness.lease.attempt_id)
        assert app.inspect_governed_agent_text(
            witness.lease.attempt_id) == "RECEIVER_START_UNKNOWN"
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()
