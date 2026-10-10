"""Fake-only Codex registry recovery bound to the durable agent start."""

import json
import sqlite3
from dataclasses import asdict

import pytest

from tests.hermes_core.test_codex_adapter import success_jsonl
from tests.hermes_core.test_ea4e92gd_codex_terminal_ping import codex_outcome
from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tools.hermes_core.agent_codex_terminal_witness import load_codex_terminal_candidate
from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.codex_adapter import CodexInvocationRegistry, CodexProcessResult
from tools.hermes_core.delegated_task import DelegationIntegrityError


def durable_codex_record(tmp_path, witness, *, pid=1234, statement=None,
                         returncode=0, launch_id=None):
    registry = CodexInvocationRegistry(str(tmp_path / "codex-transport.sqlite3"))
    registry.initialize()
    invocation = witness.bound.invocation
    registry.reserve(
        key=invocation.idempotency_key, material_hash="a" * 64,
        run_id=invocation.runtime_run_id,
        launch_id=launch_id or invocation.lineage.launch_attempt_id,
        delegation_id=invocation.lineage.delegation_id,
        argv_hash="b" * 64,
    )
    body = codex_outcome(witness).verified_result.payload
    if statement is not None:
        body["result_payload"]["statement"] = statement
    process = CodexProcessResult(
        pid=pid, returncode=returncode, stdout=success_jsonl(), stderr="",
        final_output=json.dumps(body),
    )
    registry.transition(
        invocation.idempotency_key, start_state="DEFINITELY_STARTED",
        terminal_state="VERIFIED", pid=1234,
        result_json=json.dumps(asdict(process)),
    )
    return registry


def test_codex_registry_reverifies_ping_after_restart(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        registry = durable_codex_record(tmp_path, witness)
        reopened = CodexInvocationRegistry(registry.path)
        candidate = load_codex_terminal_candidate(witness, reopened)
        assert validate_agent_ping_candidate(
            witness.task, witness.lease, witness.receipt, candidate,
        ).receipt_hash == witness.receipt.artifact_hash
    finally:
        start.close()


def test_codex_registry_without_terminal_time_denied(tmp_path):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        registry = durable_codex_record(tmp_path, witness)
        with sqlite3.connect(registry.path) as conn:
            conn.execute(
                "UPDATE codex_transport_invocations SET terminal_observed_at=NULL"
            )
        with pytest.raises(DelegationIntegrityError, match="terminal result missing"):
            load_codex_terminal_candidate(witness, registry)
    finally:
        start.close()


@pytest.mark.parametrize("forgery", ["missing", "pid", "statement", "exit", "launch"])
def test_codex_registry_forgery_denied(tmp_path, forgery):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "codex-cli-agent", ping=True,
    )
    try:
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        registry = CodexInvocationRegistry(str(tmp_path / "empty.sqlite3"))
        registry.initialize()
        if forgery != "missing":
            registry = durable_codex_record(
                tmp_path, witness,
                pid=999 if forgery == "pid" else 1234,
                statement="forged" if forgery == "statement" else None,
                returncode=1 if forgery == "exit" else 0,
                launch_id="other" if forgery == "launch" else None,
            )
        with pytest.raises(DelegationIntegrityError):
            load_codex_terminal_candidate(witness, registry)
    finally:
        start.close()
