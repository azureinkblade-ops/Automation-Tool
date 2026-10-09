"""Fake-only launch-to-delegation binding; no adapter, process, or network."""

import hashlib
from dataclasses import replace

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_receiver_lineage import bind_agent_invocation
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.execution_start import (
    ExecutionLauncherActor, ExecutionLauncherActorType, build_execution_launch_attempt,
)


def artifacts(agent, **launch_changes):
    task = make_envelope(requested_target_agent_id=agent)
    lease = make_lease(task)
    values = {
        "launch_attempt_id": "launch-1", "reservation_id": "reservation-1",
        "reservation_hash": "1" * 64, "route_id": lease.route_id,
        "route_hash": lease.route_hash, "attempt_id": lease.attempt_id,
        "attempt_hash": lease.attempt_hash, "authorization_id": lease.authorization_id,
        "authorization_hash": lease.authorization_hash, "task_id": task.task_id,
        "worker_id": agent, "worker_class": agent, "worker_version": "1",
        "operation": task.operation, "input_hash": task.artifact_hash,
        "runtime_binding_id": "binding-1", "runtime_binding_version": "1",
        "runtime_binding_hash": "2" * 64, "idempotency_key": "send-once-1",
        "recorded_at": "2026-08-27T12:05:00Z",
        "must_start_by": "2026-08-27T12:06:00Z",
        "launcher_actor": ExecutionLauncherActor(
            actor_id="test-launcher",
            actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
            actor_context="fake-only",
        ),
    }
    values.update(launch_changes)
    launch = build_execution_launch_attempt(**values)
    if agent == "kilo-cli-agent":
        runtime = launch.launch_attempt_id
    else:
        prefix = "codex-run-" if agent == "codex-cli-agent" else "opencode-run-"
        runtime = prefix + hashlib.sha256(launch.idempotency_key.encode()).hexdigest()[:32]
    receipt = make_receipt(
        task, lease, launch_attempt_id=launch.launch_attempt_id,
        launch_attempt_hash=launch.artifact_hash, runtime_run_id=runtime,
    )
    return task, lease, receipt, launch


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_existing_launch_and_runtime_identity_bind(agent):
    task, lease, receipt, launch = artifacts(agent)
    bound = bind_agent_invocation(task, lease, receipt, launch, receiver_agent_id=agent)
    assert bound.lineage.delegation_id == task.delegation_id
    assert bound.idempotency_key == launch.idempotency_key
    assert bound.runtime_run_id == receipt.runtime_run_id
    assert bound.launch_attempt_hash == launch.artifact_hash


@pytest.mark.parametrize("change", [
    {"worker_id": "other-agent"},
    {"attempt_id": "other-attempt"},
    {"input_hash": "9" * 64},
    {"idempotency_key": "different-send"},
])
def test_divergent_launch_is_denied(change):
    task, lease, receipt, _ = artifacts("opencode-cli-agent")
    _, _, _, launch = artifacts("opencode-cli-agent", **change)
    with pytest.raises(DelegationIntegrityError):
        bind_agent_invocation(task, lease, receipt, launch,
                              receiver_agent_id="opencode-cli-agent")


def test_tampered_launch_and_runtime_claim_are_denied():
    task, lease, receipt, launch = artifacts("kilo-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        bind_agent_invocation(task, lease, receipt, replace(launch, worker_id="other"),
                              receiver_agent_id="kilo-cli-agent")
    wrong_runtime = make_receipt(
        task, lease, launch_attempt_id=launch.launch_attempt_id,
        launch_attempt_hash=launch.artifact_hash, runtime_run_id="other-run",
    )
    with pytest.raises(DelegationIntegrityError):
        bind_agent_invocation(task, lease, wrong_runtime, launch,
                              receiver_agent_id="kilo-cli-agent")


@pytest.mark.parametrize("key", [None, ""])
def test_missing_launch_idempotency_key_is_denied(key):
    task, lease, receipt, launch = artifacts("opencode-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        bind_agent_invocation(task, lease, receipt,
                              replace(launch, idempotency_key=key),
                              receiver_agent_id="opencode-cli-agent")
