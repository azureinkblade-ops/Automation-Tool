"""Pure lineage binding for an already accepted delegated receiver task."""

from dataclasses import dataclass

from tools.hermes_core.delegated_task import (
    DelegatedCapabilityLease,
    DelegatedTaskEnvelope,
    DelegationIntegrityError,
)
from tools.hermes_core.delegation_delivery import DelegationReceipt


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
