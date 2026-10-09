"""Fake terminal Kilo/OpenCode transport bound to real temporary start stores."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tools.hermes_core.agent_ping_terminal import compose_terminal_text_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.receiver_adapter import ExecutionOutcome, InvocationRecord, VerifiedResult


def terminal_outcome(witness, *, statement=None):
    agent = witness.receipt.receiver_agent_id
    body = {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": witness.task.task_input_hash,
            "receiver_receipt_hash": witness.receipt.artifact_hash,
            "statement": statement or f"{agent}:PING_OK",
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            "sha256": witness.receipt.artifact_hash,
        }],
        "error_code": None, "error_summary": None,
    }
    invocation = witness.bound.invocation
    return ExecutionOutcome(
        process_started=True, replayed=False,
        record=InvocationRecord(
            idempotency_key=invocation.idempotency_key,
            runtime_run_id=invocation.runtime_run_id,
            start_state="started", pid=1234, argv_hash="a" * 64,
            terminal_state="completed" if agent == "kilo-cli-agent" else "TERMINAL",
        ),
        verified_result=VerifiedResult(
            valid=True, payload={"type": "text", "text": canonical_json(body)},
        ),
    )


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_durable_start_and_terminal_text_compose_no_output_ping(tmp_path, agent):
    authority, store, task, lease, receipt, _ = stores_and_artifacts(
        tmp_path, agent, ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, store, lease.attempt_id)
        result = compose_terminal_text_ping(
            witness, terminal_outcome(witness),
            completed_at="2026-08-27T12:05:04Z",
        )
        assert result.outcome == "SUCCEEDED"
        assert result.output_manifest == ()
        assert result.receipt_hash == receipt.artifact_hash
        assert result.result_payload["task_input_hash"] == task.task_input_hash
    finally:
        store.close()


@pytest.mark.parametrize("forgery", ["send", "runtime", "terminal", "statement"])
def test_terminal_text_forgery_does_not_compose(tmp_path, forgery):
    authority, store, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, store, lease.attempt_id)
        outcome = terminal_outcome(
            witness, statement="forged" if forgery == "statement" else None,
        )
        if forgery == "send":
            outcome = replace(outcome, record=replace(outcome.record, idempotency_key="other"))
        elif forgery == "runtime":
            outcome = replace(outcome, record=replace(outcome.record, runtime_run_id="other"))
        elif forgery == "terminal":
            outcome = replace(outcome, record=replace(outcome.record, terminal_state="error"))
        with pytest.raises(DelegationIntegrityError):
            compose_terminal_text_ping(
                witness, outcome, completed_at="2026-08-27T12:05:04Z",
            )
    finally:
        store.close()
