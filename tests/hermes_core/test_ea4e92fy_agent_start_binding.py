"""Fake-only exact start binding for three delegated agents."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fq_agent_invocation_binding import artifacts
from tools.hermes_core.agent_receiver_lineage import (
    bind_agent_invocation, bind_agent_start_result,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.execution_start import (
    ExecutionStartOutcome, build_execution_start_result,
)


def start_for(launch, expected_runtime, **changes):
    values = {
        "launch_attempt_id": launch.launch_attempt_id,
        "launch_attempt_hash": launch.artifact_hash,
        "reservation_id": launch.reservation_id,
        "reservation_hash": launch.reservation_hash,
        "route_id": launch.route_id,
        "route_hash": launch.route_hash,
        "task_id": launch.task_id,
        "worker_id": launch.worker_id,
        "worker_version": launch.worker_version,
        "runtime_binding_id": launch.runtime_binding_id,
        "runtime_binding_version": launch.runtime_binding_version,
        "runtime_binding_hash": launch.runtime_binding_hash,
        "idempotency_key": launch.idempotency_key,
        "outcome": ExecutionStartOutcome.STARTED,
        "recorded_at": "2026-08-27T12:05:01Z",
        "runtime_run_id": expected_runtime,
        "runtime_evidence_hash": "3" * 64,
    }
    values.update(changes)
    return build_execution_start_result(**values)


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_exact_started_artifact_binds_agent_launch(agent):
    task, lease, receipt, launch = artifacts(agent)
    invocation = bind_agent_invocation(
        task, lease, receipt, launch, receiver_agent_id=agent,
    )
    start = start_for(launch, invocation.runtime_run_id)
    bound = bind_agent_start_result(invocation, launch, start)
    assert bound.start_result_id == start.start_result_id
    assert bound.start_result_hash == start.artifact_hash
    assert bound.runtime_evidence_hash == start.runtime_evidence_hash


@pytest.mark.parametrize("change", [
    {"launch_attempt_hash": "4" * 64},
    {"reservation_hash": "4" * 64},
    {"worker_id": "other-agent"},
    {"runtime_binding_hash": "4" * 64},
    {"idempotency_key": "another-send"},
    {"runtime_run_id": "another-runtime"},
    {"runtime_evidence_hash": None},
    {"runtime_evidence_hash": "not-a-hash"},
])
def test_divergent_start_claim_is_denied(change):
    task, lease, receipt, launch = artifacts("kilo-cli-agent")
    invocation = bind_agent_invocation(
        task, lease, receipt, launch, receiver_agent_id="kilo-cli-agent",
    )
    start = start_for(launch, invocation.runtime_run_id, **change)
    with pytest.raises(DelegationIntegrityError):
        bind_agent_start_result(invocation, launch, start)


def test_absent_unknown_failed_and_tampered_start_are_denied():
    task, lease, receipt, launch = artifacts("opencode-cli-agent")
    invocation = bind_agent_invocation(
        task, lease, receipt, launch, receiver_agent_id="opencode-cli-agent",
    )
    cases = [
        None,
        start_for(launch, None, outcome=ExecutionStartOutcome.UNKNOWN,
                  runtime_evidence_hash=None),
        start_for(launch, None, outcome=ExecutionStartOutcome.FAILED,
                  runtime_evidence_hash=None, error_code="NO_START"),
        replace(start_for(launch, invocation.runtime_run_id), worker_id="tampered"),
    ]
    for start in cases:
        with pytest.raises(DelegationIntegrityError):
            bind_agent_start_result(invocation, launch, start)
