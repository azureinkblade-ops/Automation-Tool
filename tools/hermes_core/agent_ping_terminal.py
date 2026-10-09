"""Pure terminal transport to canonical no-output agent ping results."""

from tools.hermes_core.agent_ping_result import build_validated_agent_ping_result
from tools.hermes_core.agent_result_candidate import (
    AgentResultCandidate, bind_terminal_agent_candidate,
)
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.codex_adapter import (
    CodexExecutionOutcome, CodexInvocationRecord, CodexVerifiedResult,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.delegation_result import DelegationResult
from tools.hermes_core.hashing import canonical_json
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


def compose_codex_structured_ping(
    witness: DurableAgentStart,
    outcome: CodexExecutionOutcome,
    *,
    completed_at: str,
) -> DelegationResult:
    """Bind Codex's structured terminal artifact; no runtime authority is granted."""
    if (type(witness) is not DurableAgentStart
            or witness.bound.invocation.lineage.receiver_agent_id != "codex-cli-agent"
            or type(outcome) is not CodexExecutionOutcome):
        raise DelegationIntegrityError("Codex ping inputs denied")
    invocation = witness.bound.invocation
    record = outcome.record
    verified = outcome.verified_result
    if (type(record) is not CodexInvocationRecord
            or type(verified) is not CodexVerifiedResult
            or not outcome.process_started or outcome.replayed
            or record.idempotency_key != invocation.idempotency_key
            or record.runtime_run_id != invocation.runtime_run_id
            or record.launch_attempt_id != invocation.lineage.launch_attempt_id
            or record.delegation_id != invocation.lineage.delegation_id
            or record.start_state != "DEFINITELY_STARTED"
            or record.terminal_state != "VERIFIED"
            or type(record.pid) is not int or record.pid <= 0
            or not verified.valid or not verified.process_exit_success
            or verified.outcome != "SUCCEEDED"
            or type(verified.payload) is not dict):
        raise DelegationIntegrityError("Codex terminal identity or state mismatch")
    candidate = AgentResultCandidate(
        lineage=invocation.lineage,
        candidate_json=canonical_json(verified.payload),
    )
    return build_validated_agent_ping_result(
        witness.task, witness.lease, witness.receipt, candidate,
        started_at=witness.start_result.recorded_at,
        completed_at=completed_at,
    )
