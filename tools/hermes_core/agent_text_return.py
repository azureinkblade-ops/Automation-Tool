"""Recover one bounded agent text result without starting a receiver."""

from tools.hermes_core.agent_codex_terminal_witness import load_codex_terminal_observation
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_result import (
    AGENT_TEXT_SCHEMA_ID, build_validated_agent_text_result,
)
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def return_bound_agent_text(
    authority: SQLiteDelegationStore,
    start: SQLiteExecutionStartStore,
    captures: SQLiteAgentTerminalCaptureStore,
    registry: CodexInvocationRegistry,
    results: SQLiteDelegationResultStore,
    attempt_id: str,
):
    """Deliver captured text to the originator once; never invoke an agent."""
    if (type(authority) is not SQLiteDelegationStore
            or type(start) is not SQLiteExecutionStartStore
            or type(captures) is not SQLiteAgentTerminalCaptureStore
            or type(registry) is not CodexInvocationRegistry
            or type(results) is not SQLiteDelegationResultStore
            or captures.authority.path != authority.path
            or captures.start is not start
            or results.path != authority.path):
        raise DelegationIntegrityError("agent text stores are not bound")
    receipt = authority.get_receipt(attempt_id)
    task = authority.get_delegation(receipt.delegation_id)
    if (task.expected_result_schema_id != AGENT_TEXT_SCHEMA_ID
            or receipt.receiver_agent_id not in {
                "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
            }):
        raise DelegationIntegrityError("bounded agent text return is not supported")
    try:
        existing = results.get_result(attempt_id)
    except DelegationNotFoundError:
        existing = None
    if existing is not None:
        return results.record_verified_result_and_delivery(
            existing, validated_result_schema_id=AGENT_TEXT_SCHEMA_ID,
            delivered_at=None,
        )
    witness = load_bound_agent_start(authority, start, attempt_id)
    if receipt.receiver_agent_id == "codex-cli-agent":
        observation = load_codex_terminal_observation(witness, registry)
        candidate, completed_at = observation.candidate, observation.completed_at
    else:
        captured = captures.get(attempt_id)
        if captured is None:
            raise DelegationIntegrityError("terminal capture is absent; outcome remains unknown")
        candidate, completed_at = captured.candidate, captured.captured_at
    result = build_validated_agent_text_result(
        witness.task, witness.lease, witness.receipt, candidate,
        started_at=witness.start_result.recorded_at,
        completed_at=completed_at,
    )
    return results.record_verified_result_and_delivery(
        result, validated_result_schema_id=AGENT_TEXT_SCHEMA_ID,
        delivered_at=None,
    )
