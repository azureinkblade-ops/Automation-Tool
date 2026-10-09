"""Fake Codex structured terminal result bound to a durable STARTED artifact."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tools.hermes_core.agent_ping_terminal import compose_codex_structured_ping
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import (
    CodexExecutionOutcome, CodexInvocationRecord, CodexVerifiedResult,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def codex_outcome(witness):
    invocation = witness.bound.invocation
    receipt_hash = witness.receipt.artifact_hash
    body = {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": witness.task.task_input_hash,
            "receiver_receipt_hash": receipt_hash,
            "statement": "codex-cli-agent:PING_OK",
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            "sha256": receipt_hash,
        }],
        "error_code": None, "error_summary": None,
    }
    return CodexExecutionOutcome(
        record=CodexInvocationRecord(
            idempotency_key=invocation.idempotency_key,
            material_hash="a" * 64,
            runtime_run_id=invocation.runtime_run_id,
            launch_attempt_id=invocation.lineage.launch_attempt_id,
            delegation_id=invocation.lineage.delegation_id,
            argv_hash="b" * 64,
            start_state="DEFINITELY_STARTED", terminal_state="VERIFIED", pid=1234,
            result_json=None, cancellation_reason=None,
        ),
        verified_result=CodexVerifiedResult(
            valid=True, outcome="SUCCEEDED", payload=body,
            error=None, process_exit_success=True,
        ),
        process_started=True, replayed=False,
    )


def test_codex_structured_terminal_composes_no_output_ping(tmp_path):
    authority, store, task, lease, receipt, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, store, lease.attempt_id)
        result = compose_codex_structured_ping(
            witness, codex_outcome(witness), completed_at="2026-08-27T12:05:04Z",
        )
        assert result.outcome == "SUCCEEDED"
        assert result.output_manifest == ()
        assert result.receipt_hash == receipt.artifact_hash
        assert result.result_payload["task_input_hash"] == task.task_input_hash
    finally:
        store.close()


@pytest.mark.parametrize("forgery", [
    "send", "runtime", "launch", "delegation", "start", "terminal",
    "process", "exit", "valid", "statement", "evidence", "output",
])
def test_codex_structured_terminal_forgery_denied(tmp_path, forgery):
    authority, store, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, store, lease.attempt_id)
        outcome = codex_outcome(witness)
        if forgery in {"send", "runtime", "launch", "delegation", "start", "terminal"}:
            field = {
                "send": "idempotency_key", "runtime": "runtime_run_id",
                "launch": "launch_attempt_id", "delegation": "delegation_id",
                "start": "start_state", "terminal": "terminal_state",
            }[forgery]
            outcome = replace(outcome, record=replace(outcome.record, **{field: "forged"}))
        elif forgery == "process":
            outcome = replace(outcome, process_started=False)
        elif forgery == "exit":
            outcome = replace(outcome, verified_result=replace(
                outcome.verified_result, process_exit_success=False,
            ))
        elif forgery == "valid":
            outcome = replace(outcome, verified_result=replace(
                outcome.verified_result, valid=False,
            ))
        else:
            body = dict(outcome.verified_result.payload)
            if forgery == "statement":
                body["result_payload"] = dict(body["result_payload"], statement="forged")
            elif forgery == "evidence":
                body["evidence_manifest"] = []
            else:
                body["output_manifest"] = [{"sha256": "a" * 64}]
            outcome = replace(outcome, verified_result=replace(
                outcome.verified_result, payload=body,
            ))
        with pytest.raises(DelegationIntegrityError):
            compose_codex_structured_ping(
                witness, outcome, completed_at="2026-08-27T12:05:04Z",
            )
    finally:
        store.close()
