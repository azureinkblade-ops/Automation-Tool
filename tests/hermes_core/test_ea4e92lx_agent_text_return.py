"""Fake terminal text from three agents returns through durable recovery."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92gk_codex_terminal_witness import durable_codex_record
from tests.hermes_core.test_ea4e92gm_codex_ping_return import clock
from tests.hermes_core.test_ea4e92lw_agent_text_result import DELIVERY_TIME, EVIDENCE
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_result import AGENT_TEXT_SCHEMA_ID
from tools.hermes_core.agent_text_return import return_bound_agent_text
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


AGENTS = ("codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent")


def body_for(witness, text="The bounded answer"):
    return {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": witness.task.task_input_hash,
            "receiver_receipt_hash": witness.receipt.artifact_hash,
            "text": text,
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            "sha256": witness.receipt.artifact_hash,
        }],
        "error_code": None, "error_summary": None,
    }


def ready(tmp_path, agent, *, capture=True):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, task_changes={
            "expected_result_schema_id": AGENT_TEXT_SCHEMA_ID,
            "expected_evidence": EVIDENCE,
        },
    )
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
    registry.initialize()
    if capture:
        if agent == "codex-cli-agent":
            registry = durable_codex_record(
                tmp_path, witness, body=body_for(witness),
                clock=clock("2026-08-27T12:05:04Z"),
            )
        else:
            outcome = terminal_outcome(witness)
            outcome = replace(
                outcome, verified_result=replace(
                    outcome.verified_result,
                    payload={"type": "text", "text": canonical_json(body_for(witness))},
                ),
            )
            capture_store(authority, start).capture(lease.attempt_id, outcome)
    return authority, start, task, lease, registry


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_text_returns_once_after_store_restart(tmp_path, agent):
    authority, start, task, lease, registry = ready(tmp_path, agent)
    start.close()
    start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        authority = SQLiteDelegationStore(authority.path)
        captures = capture_store(authority, start)
        results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
        first = return_bound_agent_text(
            authority, start, captures, registry, results, lease.attempt_id,
        )
        assert first[0].result_payload["text"] == "The bounded answer"
        assert authority.get_message(first[2]).recipient_agent_id == task.originator_agent_id
        assert return_bound_agent_text(
            authority, start, captures, registry, results, lease.attempt_id,
        ) == first
        assert len(authority.list_mailbox(task.originator_agent_id)) == 1
    finally:
        start.close()


@pytest.mark.parametrize("agent", AGENTS)
def test_missing_terminal_evidence_never_delivers_text(tmp_path, agent):
    authority, start, task, lease, registry = ready(tmp_path, agent, capture=False)
    try:
        results = SQLiteDelegationResultStore(authority.path)
        with pytest.raises(DelegationIntegrityError):
            return_bound_agent_text(
                authority, start, capture_store(authority, start),
                registry, results, lease.attempt_id,
            )
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


def test_ping_schema_cannot_enter_text_return(tmp_path):
    authority, start, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        with pytest.raises(DelegationIntegrityError, match="not supported"):
            return_bound_agent_text(
                authority, start, capture_store(authority, start),
                registry, SQLiteDelegationResultStore(authority.path), lease.attempt_id,
            )
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()


@pytest.mark.parametrize("case", ["cancelled", "expired"])
def test_inactive_text_authority_never_delivers(tmp_path, case):
    authority, start, task, lease, registry = ready(tmp_path, "kilo-cli-agent")
    try:
        if case == "cancelled":
            authority.cancel_delegation(
                task.delegation_id, reason="operator cancellation",
                cancelled_at="2026-08-27T12:05:04Z",
            )
        when = (datetime(2026, 8, 27, 12, 10, 1, tzinfo=timezone.utc)
                if case == "expired" else DELIVERY_TIME)
        results = SQLiteDelegationResultStore(authority.path, clock=lambda: when)
        with pytest.raises(DelegationIntegrityError):
            return_bound_agent_text(
                authority, start, capture_store(authority, start),
                registry, results, lease.attempt_id,
            )
        with pytest.raises(DelegationNotFoundError):
            results.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []
    finally:
        start.close()
