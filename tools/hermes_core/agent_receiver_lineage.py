"""Pure lineage binding for an already accepted delegated receiver task."""

import hashlib
from dataclasses import dataclass

from tools.hermes_core.delegated_task import (
    DelegatedCapabilityLease,
    DelegatedTaskEnvelope,
    DelegationIntegrityError,
)
from tools.hermes_core.delegation_delivery import DelegationReceipt
from tools.hermes_core.execution_start import (
    ExecutionLaunchAttempt, ExecutionLaunchAttemptStatus,
    ExecutionStartOutcome, ExecutionStartResult,
)
from tools.hermes_core.hashing import sha256_payload


SUPPORTED_AGENT_IDS = frozenset({
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
})


@dataclass(frozen=True)
class BoundReceiverLineage:
    receiver_agent_id: str
    delegation_id: str
    delegated_task_hash: str
    capability_lease_id: str
    authorization_id: str
    attempt_id: str
    launch_attempt_id: str
    runtime_run_id: str
    task_input_hash: str
    expected_result_schema_id: str


@dataclass(frozen=True)
class BoundAgentInvocation:
    lineage: BoundReceiverLineage
    launch_attempt_hash: str
    idempotency_key: str
    runtime_run_id: str


@dataclass(frozen=True)
class BoundAgentStart:
    invocation: BoundAgentInvocation
    start_result_id: str
    start_result_hash: str
    runtime_evidence_hash: str


def bind_receiver_lineage(
    envelope: DelegatedTaskEnvelope,
    lease: DelegatedCapabilityLease,
    receipt: DelegationReceipt,
    *,
    receiver_agent_id: str,
) -> BoundReceiverLineage:
    """Bind canonical artifacts; durable truth and runtime authority are separate."""
    if (type(envelope) is not DelegatedTaskEnvelope
            or type(lease) is not DelegatedCapabilityLease
            or type(receipt) is not DelegationReceipt):
        raise DelegationIntegrityError("receiver lineage artifacts denied")
    envelope.verify_hash()
    lease.verify_hash()
    receipt.verify_hash()
    if (type(receiver_agent_id) is not str
            or receiver_agent_id not in SUPPORTED_AGENT_IDS
            or receipt.outcome != "ACCEPTED"):
        raise DelegationIntegrityError("receiver is not accepted")
    checks = (
        (envelope.requested_target_agent_id, receiver_agent_id),
        (lease.recipient_agent_id, receiver_agent_id),
        (receipt.receiver_agent_id, receiver_agent_id),
        (lease.delegation_id, envelope.delegation_id),
        (receipt.delegation_id, envelope.delegation_id),
        (lease.delegated_task_hash, envelope.artifact_hash),
        (receipt.delegated_task_hash, envelope.artifact_hash),
        (receipt.capability_lease_id, lease.lease_id),
        (receipt.capability_lease_hash, lease.artifact_hash),
        (receipt.authorization_id, lease.authorization_id),
        (receipt.authorization_hash, lease.authorization_hash),
        (receipt.attempt_id, lease.attempt_id),
        (receipt.attempt_hash, lease.attempt_hash),
        (receipt.route_id, lease.route_id),
        (receipt.route_hash, lease.route_hash),
        (receipt.receiver_descriptor_hash, lease.worker_descriptor_hash),
        (lease.allowed_operation, envelope.operation),
        (lease.expected_result_schema_id, envelope.expected_result_schema_id),
    )
    if any(actual != expected for actual, expected in checks):
        raise DelegationIntegrityError("receiver lineage mismatch")
    return BoundReceiverLineage(
        receiver_agent_id=receiver_agent_id,
        delegation_id=envelope.delegation_id,
        delegated_task_hash=envelope.artifact_hash,
        capability_lease_id=lease.lease_id,
        authorization_id=lease.authorization_id,
        attempt_id=lease.attempt_id,
        launch_attempt_id=receipt.launch_attempt_id,
        runtime_run_id=receipt.runtime_run_id,
        task_input_hash=envelope.task_input_hash,
        expected_result_schema_id=envelope.expected_result_schema_id,
    )


def bind_agent_invocation(
    envelope: DelegatedTaskEnvelope,
    lease: DelegatedCapabilityLease,
    receipt: DelegationReceipt,
    launch: ExecutionLaunchAttempt,
    *,
    receiver_agent_id: str,
) -> BoundAgentInvocation:
    """Project an existing admitted launch; this does not persist or execute it."""
    lineage = bind_receiver_lineage(
        envelope, lease, receipt, receiver_agent_id=receiver_agent_id,
    )
    if (type(launch) is not ExecutionLaunchAttempt or not launch.verify_hash()
            or launch.status != ExecutionLaunchAttemptStatus.RECORDED
            or type(launch.idempotency_key) is not str or not launch.idempotency_key):
        raise DelegationIntegrityError("launch artifact denied")
    checks = (
        (launch.launch_attempt_id, receipt.launch_attempt_id),
        (launch.artifact_hash, receipt.launch_attempt_hash),
        (launch.route_id, lease.route_id),
        (launch.route_hash, lease.route_hash),
        (launch.attempt_id, lease.attempt_id),
        (launch.attempt_hash, lease.attempt_hash),
        (launch.authorization_id, lease.authorization_id),
        (launch.authorization_hash, lease.authorization_hash),
        (launch.task_id, envelope.task_id),
        (launch.worker_id, receiver_agent_id),
        (launch.operation, envelope.operation),
        (launch.input_hash, envelope.artifact_hash),
    )
    if any(actual != expected for actual, expected in checks):
        raise DelegationIntegrityError("launch and delegation lineage mismatch")
    if receiver_agent_id == "kilo-cli-agent":
        runtime_run_id = launch.launch_attempt_id
    else:
        digest = hashlib.sha256(launch.idempotency_key.encode("utf-8")).hexdigest()[:32]
        prefix = "codex-run-" if receiver_agent_id == "codex-cli-agent" else "opencode-run-"
        runtime_run_id = prefix + digest
    if receipt.runtime_run_id != runtime_run_id:
        raise DelegationIntegrityError("receiver runtime identity mismatch")
    return BoundAgentInvocation(
        lineage=lineage, launch_attempt_hash=launch.artifact_hash,
        idempotency_key=launch.idempotency_key, runtime_run_id=runtime_run_id,
    )


def bind_agent_start_result(
    invocation: BoundAgentInvocation,
    launch: ExecutionLaunchAttempt,
    start_result: ExecutionStartResult | None,
) -> BoundAgentStart:
    """Bind a supplied STARTED artifact; its durable-store provenance is separate."""
    if (type(invocation) is not BoundAgentInvocation
            or type(launch) is not ExecutionLaunchAttempt
            or type(start_result) is not ExecutionStartResult
            or not launch.verify_hash() or not start_result.verify_hash()
            or start_result.outcome != ExecutionStartOutcome.STARTED):
        raise DelegationIntegrityError("agent start result is not verified STARTED")
    expected_id = sha256_payload({
        "schema": "ea4d4-start-result-id-v1",
        "launch_attempt_id": launch.launch_attempt_id,
    })
    checks = (
        (start_result.start_result_id, expected_id),
        (start_result.start_result_version, "1"),
        (start_result.launch_attempt_id, launch.launch_attempt_id),
        (start_result.launch_attempt_hash, launch.artifact_hash),
        (start_result.reservation_id, launch.reservation_id),
        (start_result.reservation_hash, launch.reservation_hash),
        (start_result.route_id, launch.route_id),
        (start_result.route_hash, launch.route_hash),
        (start_result.task_id, launch.task_id),
        (start_result.worker_id, invocation.lineage.receiver_agent_id),
        (start_result.worker_version, launch.worker_version),
        (start_result.runtime_binding_id, launch.runtime_binding_id),
        (start_result.runtime_binding_version, launch.runtime_binding_version),
        (start_result.runtime_binding_hash, launch.runtime_binding_hash),
        (start_result.idempotency_key, invocation.idempotency_key),
        (start_result.runtime_run_id, invocation.runtime_run_id),
        (invocation.lineage.launch_attempt_id, launch.launch_attempt_id),
        (invocation.launch_attempt_hash, launch.artifact_hash),
    )
    if (any(actual != expected for actual, expected in checks)
            or type(start_result.runtime_evidence_hash) is not str
            or len(start_result.runtime_evidence_hash) != 64
            or any(char not in "0123456789abcdef" for char in start_result.runtime_evidence_hash)
            or start_result.error_code is not None
            or start_result.error_summary is not None):
        raise DelegationIntegrityError("agent start result lineage mismatch")
    return BoundAgentStart(
        invocation=invocation,
        start_result_id=start_result.start_result_id,
        start_result_hash=start_result.artifact_hash,
        runtime_evidence_hash=start_result.runtime_evidence_hash,
    )
