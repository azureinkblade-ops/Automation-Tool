"""Read-only cross-store witness for a named agent's durable STARTED artifact."""

from dataclasses import dataclass

from tools.hermes_core.agent_receiver_lineage import (
    BoundAgentStart, bind_agent_invocation, bind_agent_start_result,
)
from tools.hermes_core.delegated_task import (
    DelegatedCapabilityLease, DelegatedTaskEnvelope, DelegationIntegrityError,
)
from tools.hermes_core.delegation_delivery import DelegationReceipt
from tools.hermes_core.execution_start import ExecutionLaunchAttempt, ExecutionStartResult
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


@dataclass(frozen=True)
class DurableAgentStart:
    task: DelegatedTaskEnvelope
    lease: DelegatedCapabilityLease
    receipt: DelegationReceipt
    launch: ExecutionLaunchAttempt
    start_result: ExecutionStartResult
    bound: BoundAgentStart


def load_bound_agent_start(
    authority_store: SQLiteDelegationStore,
    start_store: SQLiteExecutionStartStore,
    attempt_id: str,
) -> DurableAgentStart:
    """Read and bind durable artifacts; no cancellation check or capability grant."""
    if (type(authority_store) is not SQLiteDelegationStore
            or type(start_store) is not SQLiteExecutionStartStore
            or type(attempt_id) is not str or not attempt_id):
        raise DelegationIntegrityError("agent start stores or attempt identity denied")
    receipt = authority_store.get_receipt(attempt_id)
    task = authority_store.get_delegation(receipt.delegation_id)
    lease = authority_store.get_lease(receipt.capability_lease_id)
    start_result = start_store.get_execution_start_result(receipt.launch_attempt_id)
    if start_result is None:
        raise DelegationIntegrityError("durable agent start result is absent")
    launch = start_store.get_launch_attempt(start_result.reservation_id)
    if launch is None:
        raise DelegationIntegrityError("durable agent launch attempt is absent")
    invocation = bind_agent_invocation(
        task, lease, receipt, launch, receiver_agent_id=receipt.receiver_agent_id,
    )
    bound = bind_agent_start_result(invocation, launch, start_result)
    return DurableAgentStart(task, lease, receipt, launch, start_result, bound)
