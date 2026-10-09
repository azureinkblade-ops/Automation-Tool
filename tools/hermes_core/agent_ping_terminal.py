"""Pure Kilo/OpenCode terminal transport to canonical no-output ping result."""

from tools.hermes_core.agent_ping_result import build_validated_agent_ping_result
from tools.hermes_core.agent_result_candidate import bind_terminal_agent_candidate
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.delegation_result import DelegationResult
from tools.hermes_core.receiver_adapter import ExecutionOutcome


def compose_terminal_text_ping(
    witness: DurableAgentStart,
    outcome: ExecutionOutcome,
    *,
    completed_at: str,
) -> DelegationResult:
    """Compose a result; the trusted host still owns time, lease, and delivery."""
    if (type(witness) is not DurableAgentStart
            or witness.bound.invocation.lineage.receiver_agent_id
            not in {"kilo-cli-agent", "opencode-cli-agent"}):
        raise DelegationIntegrityError("terminal text ping receiver denied")
    candidate = bind_terminal_agent_candidate(witness.bound.invocation, outcome)
    return build_validated_agent_ping_result(
        witness.task, witness.lease, witness.receipt, candidate,
        started_at=witness.start_result.recorded_at,
        completed_at=completed_at,
    )
