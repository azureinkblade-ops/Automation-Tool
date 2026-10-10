"""Read-only recovery of a Codex terminal artifact from its durable registry."""

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_ping_terminal import bind_codex_structured_candidate
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.codex_adapter import (
    CodexAdapterError, CodexExecutionOutcome, CodexInvocationRegistry, CodexProcessResult,
    verify_process_result,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError, _parse_timestamp


@dataclass(frozen=True)
class CodexTerminalObservation:
    candidate: AgentResultCandidate
    completed_at: str


def _load_codex_terminal_record(
    witness: DurableAgentStart, registry: CodexInvocationRegistry,
):
    """Reverify persisted process bytes; do not infer or synthesize terminal time."""
    if (type(witness) is not DurableAgentStart
            or type(registry) is not CodexInvocationRegistry
            or witness.receipt.receiver_agent_id != "codex-cli-agent"):
        raise DelegationIntegrityError("Codex terminal witness inputs denied")
    try:
        record = registry.get(witness.bound.invocation.idempotency_key)
    except (sqlite3.Error, CodexAdapterError) as exc:
        raise DelegationIntegrityError("Codex durable registry unavailable") from exc
    if (record is None or record.terminal_state != "VERIFIED"
            or type(record.result_json) is not str
            or type(record.terminal_observed_at) is not float
            or not math.isfinite(record.terminal_observed_at)
            or record.terminal_observed_at <= 0):
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
    return candidate, record


def load_codex_terminal_candidate(
    witness: DurableAgentStart, registry: CodexInvocationRegistry,
):
    return _load_codex_terminal_record(witness, registry)[0]


def load_codex_terminal_observation(
    witness: DurableAgentStart, registry: CodexInvocationRegistry,
) -> CodexTerminalObservation:
    candidate, record = _load_codex_terminal_record(witness, registry)
    try:
        observed = datetime.fromtimestamp(record.terminal_observed_at, timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise DelegationIntegrityError("Codex terminal time invalid") from exc
    if not (_parse_timestamp(witness.start_result.recorded_at) <= observed
            < _parse_timestamp(witness.lease.expires_at)):
        raise DelegationIntegrityError("Codex terminal time outside start or lease")
    return CodexTerminalObservation(
        candidate, observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
