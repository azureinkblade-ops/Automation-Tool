"""Pure identity bridge between accepted agent start and executor binding.

The returned artifact is not invocation authority. A durable owner must persist
and revalidate it before issuing authorization or attempting a receiver start.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_receiver_lineage import (
    bind_agent_invocation, bind_agent_start_result,
)
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp
from tools.hermes_core.governed_bound_executor import GovernedExecutorResolution
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_executor_binding import (
    ProductionExecutorBindingHandle, parse_iso_timestamp,
)


_TEXT_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})


@dataclass(frozen=True)
class AgentInvocationBridge:
    execution_request_id: str
    attempt_id: str
    receiver_agent_id: str
    receipt_hash: str
    launch_attempt_hash: str
    start_result_hash: str
    runtime_binding_id: str
    runtime_binding_hash: str
    executor_binding_id: str
    executor_enablement_id: str
    executor_identity: str
    executor_binding_expires_at: str
    artifact_hash: str

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "schema_version": "ea4e92he-agent-invocation-bridge-v1",
            "execution_request_id": self.execution_request_id,
            "attempt_id": self.attempt_id,
            "receiver_agent_id": self.receiver_agent_id,
            "receipt_hash": self.receipt_hash,
            "launch_attempt_hash": self.launch_attempt_hash,
            "start_result_hash": self.start_result_hash,
            "runtime_binding_id": self.runtime_binding_id,
            "runtime_binding_hash": self.runtime_binding_hash,
            "executor_binding_id": self.executor_binding_id,
            "executor_enablement_id": self.executor_enablement_id,
            "executor_identity": self.executor_identity,
            "executor_binding_expires_at": self.executor_binding_expires_at,
        }

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


def bind_agent_invocation_request(
    witness: DurableAgentStart,
    resolution: GovernedExecutorResolution,
    *,
    now: datetime,
) -> AgentInvocationBridge:
    """Bind independent EA-4D and EA-4E identities without executing either."""
    if (type(witness) is not DurableAgentStart
            or type(resolution) is not GovernedExecutorResolution
            or type(now) is not datetime or now.tzinfo is None
            or now.utcoffset() is None):
        raise DelegationIntegrityError("agent invocation bridge inputs denied")
    now = now.astimezone(timezone.utc)
    receiver = witness.receipt.receiver_agent_id
    if receiver not in _TEXT_RECEIVERS:
        raise DelegationIntegrityError("agent invocation bridge receiver denied")
    invocation = bind_agent_invocation(
        witness.task, witness.lease, witness.receipt, witness.launch,
        receiver_agent_id=receiver,
    )
    bound = bind_agent_start_result(
        invocation, witness.launch, witness.start_result,
    )
    if bound != witness.bound:
        raise DelegationIntegrityError("agent invocation bridge witness mismatch")
    handle = resolution.binding_handle
    if (resolution.resolution_decision != "RESOLVED"
            or type(handle) is not ProductionExecutorBindingHandle
            or resolution.executor is None
            or resolution.receiver_id != receiver
            or resolution.binding_id != handle.binding_id
            or resolution.bound_at != handle.bound_at
            or resolution.expires_at != handle.expires_at
            or handle.receiver_id != receiver
            or not handle.binding_id or not handle.enablement_id
            or not handle.executor_identity
            or handle.registry.resolve(receiver) is not resolution.executor
            or getattr(resolution.executor, "executor_id", None) != handle.executor_identity):
        raise DelegationIntegrityError("agent executor binding mismatch")
    try:
        bound_at = parse_iso_timestamp(handle.bound_at)
        expires_at = parse_iso_timestamp(handle.expires_at)
    except (TypeError, ValueError) as exc:
        raise DelegationIntegrityError("agent executor binding time invalid") from exc
    start_at = _parse_timestamp(witness.start_result.recorded_at)
    if (bound_at > now or start_at > now or now >= expires_at
            or now >= _parse_timestamp(witness.lease.expires_at)):
        raise DelegationIntegrityError("agent executor binding expired")
    request_id = "agent-exec-" + sha256_payload({
        "schema_version": "ea4e92he-agent-request-id-v1",
        "attempt_id": witness.lease.attempt_id,
        "receipt_hash": witness.receipt.artifact_hash,
        "launch_attempt_hash": witness.launch.artifact_hash,
        "start_result_hash": witness.start_result.artifact_hash,
    })
    fields = {
        "execution_request_id": request_id,
        "attempt_id": witness.lease.attempt_id,
        "receiver_agent_id": receiver,
        "receipt_hash": witness.receipt.artifact_hash,
        "launch_attempt_hash": witness.launch.artifact_hash,
        "start_result_hash": witness.start_result.artifact_hash,
        "runtime_binding_id": witness.launch.runtime_binding_id,
        "runtime_binding_hash": witness.launch.runtime_binding_hash,
        "executor_binding_id": handle.binding_id,
        "executor_enablement_id": handle.enablement_id,
        "executor_identity": handle.executor_identity,
        "executor_binding_expires_at": handle.expires_at,
    }
    artifact = AgentInvocationBridge(**fields, artifact_hash="")
    return AgentInvocationBridge(**fields, artifact_hash=sha256_payload(artifact.to_canonical_dict()))
