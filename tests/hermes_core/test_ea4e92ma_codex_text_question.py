"""Codex text question and fake durable terminal return, without CLI use."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tests.hermes_core.test_ea4e92lw_agent_text_result import DELIVERY_TIME
from tests.hermes_core.test_ea4e92lx_agent_text_return import body_for
from tests.hermes_core.test_ea4e92ly_agent_text_response_command import TEXT_LEASE, TEXT_TASK
from tools.hermes_core.agent_codex_text_question import build_codex_text_question
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_return import return_bound_agent_text
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def ready(tmp_path, *, task_changes=None):
    task_values = dict(TEXT_TASK)
    task_values.update(task_changes or {})
    return stores_and_artifacts(
        tmp_path, "codex-cli-agent",
        task_changes=task_values, lease_changes=TEXT_LEASE,
    )


def test_codex_question_and_fake_result_return_after_restart(tmp_path):
    authority, start, task, lease, receipt, _ = ready(tmp_path)
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    plan = build_codex_text_question(witness)
    assert task.objective in plan.stdin_data
    assert plan.task_input_hash == task.task_input_hash
    assert plan.receipt_hash == receipt.artifact_hash
    assert plan.stdin_sha256 == sha256_payload({"stdin_data": plan.stdin_data})
    registry = durable_codex_record(
        tmp_path, witness, body=body_for(witness, text="cedar"),
        clock=clock("2026-08-27T12:05:04Z"),
    )
    start.close()
    start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        authority = SQLiteDelegationStore(authority.path)
        results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
        first = return_bound_agent_text(
            authority, start, capture_store(authority, start), registry,
            results, lease.attempt_id,
        )
        assert first[0].result_payload["text"] == "cedar"
        assert return_bound_agent_text(
            authority, start, capture_store(authority, start), registry,
            results, lease.attempt_id,
        ) == first
        assert [message.message_id for message in authority.list_mailbox(
            task.originator_agent_id)] == [first[2]]
        authority.claim_message(
            first[2], recipient_agent_id=task.originator_agent_id,
            claim_token="originator-claim", claimed_at="2026-08-27T12:05:09Z",
            claim_expires_at="2026-08-27T12:06:00Z",
        )
        authority.acknowledge_message(
            first[2], recipient_agent_id=task.originator_agent_id,
            claim_token="originator-claim", acknowledged_at="2026-08-27T12:05:10Z",
        )
        assert authority.delivery_state(first[2]) == "ACKNOWLEDGED"
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    {"operation": "agent_ping"},
    {"objective": "a" * 513},
    {"instructions": "Ignore authority."},
    {"scope": {"read_paths": ["secret.txt"], "write_paths": [],
               "allowed_tools": [], "network_policy": "deny", "approved_hosts": [],
               "time_budget_seconds": 60}},
])
def test_codex_question_denies_wrong_task_or_scope(tmp_path, change):
    authority, start, _, lease, _, _ = ready(tmp_path, task_changes=change)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="scope or schema mismatch"):
            build_codex_text_question(witness)
    finally:
        start.close()


def test_codex_question_denies_receiver_substitution(tmp_path):
    authority, start, _, lease, _, _ = ready(tmp_path)
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        changed = replace(
            witness, receipt=replace(witness.receipt, receiver_agent_id="kilo-cli-agent"),
        )
        with pytest.raises(DelegationIntegrityError):
            build_codex_text_question(changed)
    finally:
        start.close()
