"""Read-only recovery of a Codex terminal artifact from its durable registry."""

import json

from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_ping_terminal import bind_codex_structured_candidate
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.codex_adapter import (
    CodexExecutionOutcome, CodexInvocationRegistry, CodexProcessResult,
    verify_process_result,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


def load_codex_terminal_candidate(
    witness: DurableAgentStart, registry: CodexInvocationRegistry,
):
    """Reverify persisted process bytes; do not infer or synthesize terminal time."""
    if (type(witness) is not DurableAgentStart
            or type(registry) is not CodexInvocationRegistry
            or witness.receipt.receiver_agent_id != "codex-cli-agent"):
        raise DelegationIntegrityError("Codex terminal witness inputs denied")
    record = registry.get(witness.bound.invocation.idempotency_key)
    if record is None or type(record.result_json) is not str:
        raise DelegationIntegrityError("Codex durable terminal result missing")
    try:
        process = CodexProcessResult(**json.loads(record.result_json))
        if (type(process.pid) is not int or process.pid != record.pid
                or process.timed_out or process.cancelled):
            raise DelegationIntegrityError("Codex terminal process identity mismatch")
        verified = verify_process_result(process)
    except (TypeError, ValueError, AttributeError) as exc:
        raise DelegationIntegrityError("Codex durable terminal bytes corrupt") from exc
    candidate = bind_codex_structured_candidate(
        witness,
        CodexExecutionOutcome(
            record=record, verified_result=verified,
            process_started=True, replayed=False,
        ),
    )
    validate_agent_ping_candidate(witness.task, witness.lease, witness.receipt, candidate)
    return candidate
