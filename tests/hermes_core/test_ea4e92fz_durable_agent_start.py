"""Real temporary SQLite stores, fake-only delegated agent start lineage."""

import hashlib

import pytest

from tests.hermes_core.test_ea4e92fy_agent_start_binding import start_for
from tools.hermes_core.agent_ping_result import AGENT_PING_SCHEMA_ID
from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.execution_start import (
    ExecutionLaunchAttemptStatus, ExecutionLauncherActor,
    ExecutionLauncherActorType, ExecutionStartOutcome,
    build_execution_launch_attempt, build_execution_start_reservation,
)
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def stores_and_artifacts(tmp_path, agent, *, persist_start=True, start_changes=None,
                         ping=False):
    task_values = {"requested_target_agent_id": agent}
    if ping:
        task_values.update(
            expected_result_schema_id=AGENT_PING_SCHEMA_ID,
            expected_evidence=[{
                "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            }],
        )
    task = make_envelope(**task_values)
    lease = make_lease(task)
    authority = SQLiteDelegationStore(tmp_path / "authority.sqlite3")
    authority.create_delegation(task)
    authority.issue_lease(lease)
    actor = ExecutionLauncherActor(
        actor_id="fake-launcher", actor_type=ExecutionLauncherActorType.SYSTEM_LAUNCHER,
        actor_context="fake-only",
    )
    reservation = build_execution_start_reservation(
        reservation_id="reservation-1", route_id=lease.route_id,
        route_hash=lease.route_hash, attempt_id=lease.attempt_id,
        attempt_hash=lease.attempt_hash, authorization_id=lease.authorization_id,
        authorization_hash=lease.authorization_hash, claim_id="claim-1",
        claim_hash="1" * 64, request_id="request-1", request_hash="2" * 64,
        decision_id="decision-1", decision_hash="3" * 64,
        task_id=task.task_id, worker_id=agent, worker_class=agent,
        worker_version="1", operation=task.operation, input_hash=task.artifact_hash,
        reserved_at="2026-08-27T12:05:00Z", must_start_by="2026-08-27T12:06:00Z",
        launcher_actor=actor,
    )
    launch = build_execution_launch_attempt(
        launch_attempt_id="launch-1", reservation_id=reservation.reservation_id,
        reservation_hash=reservation.artifact_hash,
        route_id=lease.route_id, route_hash=lease.route_hash,
        attempt_id=lease.attempt_id, attempt_hash=lease.attempt_hash,
        authorization_id=lease.authorization_id,
        authorization_hash=lease.authorization_hash, task_id=task.task_id,
        worker_id=agent, worker_class=agent, worker_version="1",
        operation=task.operation, input_hash=task.artifact_hash,
        runtime_binding_id="binding-1", runtime_binding_version="1",
        runtime_binding_hash="4" * 64, idempotency_key="send-once-1",
        recorded_at="2026-08-27T12:05:00Z",
        must_start_by="2026-08-27T12:06:00Z", launcher_actor=actor,
        status=ExecutionLaunchAttemptStatus.RECORDED,
    )
    runtime = launch.launch_attempt_id if agent == "kilo-cli-agent" else (
        ("codex-run-" if agent == "codex-cli-agent" else "opencode-run-")
        + hashlib.sha256(launch.idempotency_key.encode()).hexdigest()[:32]
    )
    receipt = make_receipt(
        task, lease, launch_attempt_id=launch.launch_attempt_id,
        launch_attempt_hash=launch.artifact_hash, runtime_run_id=runtime,
    )
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z",
    )
    authority.claim_message(
        message.message_id, recipient_agent_id=agent, claim_token="fake-claim",
        claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z",
    )
    authority.record_receipt(receipt, source_message_id=message.message_id)
    start_store = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    start_store.record_reservation(reservation=reservation, now="2026-08-27T12:05:00Z")
    start_store.record_launch_attempt(attempt=launch, now="2026-08-27T12:05:00Z")
    if persist_start:
        start_store.persist_execution_start_result(
            start_for(launch, runtime, **(start_changes or {})),
        )
    return authority, start_store, task, lease, receipt, launch


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_three_agents_bind_durable_start_after_store_reopen(tmp_path, agent):
    authority, start_store, task, lease, receipt, launch = stores_and_artifacts(tmp_path, agent)
    start_store.close()
    reopened = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        witness = load_bound_agent_start(authority, reopened, lease.attempt_id)
        assert witness.task == task
        assert witness.lease == lease
        assert witness.receipt == receipt
        assert witness.launch == launch
        assert witness.bound.invocation.runtime_run_id == receipt.runtime_run_id
    finally:
        reopened.close()


@pytest.mark.parametrize("start_changes", [
    None,
    {"outcome": ExecutionStartOutcome.UNKNOWN, "runtime_run_id": None,
     "runtime_evidence_hash": "5" * 64},
    {"outcome": ExecutionStartOutcome.FAILED, "runtime_run_id": None,
     "runtime_evidence_hash": "5" * 64, "error_code": "NO_START"},
    {"runtime_run_id": "wrong-runtime"},
    {"reservation_id": "unknown-reservation"},
])
def test_absent_or_nonmatching_durable_start_is_denied(tmp_path, start_changes):
    authority, start_store, _, lease, _, _ = stores_and_artifacts(
        tmp_path, "kilo-cli-agent", persist_start=start_changes is not None,
        start_changes=start_changes,
    )
    try:
        with pytest.raises(DelegationIntegrityError):
            load_bound_agent_start(authority, start_store, lease.attempt_id)
    finally:
        start_store.close()


@pytest.mark.parametrize("action", ["cancel", "revoke"])
def test_inactive_authority_is_denied_before_start_witness(tmp_path, action):
    authority, start_store, task, lease, _, _ = stores_and_artifacts(
        tmp_path, "opencode-cli-agent",
    )
    if action == "cancel":
        authority.cancel_delegation(
            task.delegation_id, reason="operator cancellation",
            cancelled_at="2026-08-27T12:05:02Z",
        )
    else:
        authority.revoke_lease(
            lease.lease_id, reason="operator revocation",
            revoked_at="2026-08-27T12:05:02Z",
        )
    try:
        with pytest.raises(DelegationIntegrityError):
            load_bound_agent_start(authority, start_store, lease.attempt_id)
    finally:
        start_store.close()
