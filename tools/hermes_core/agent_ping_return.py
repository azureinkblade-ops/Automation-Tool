"""Recover a captured text-agent ping and return it to the originator once."""

from tools.hermes_core.agent_ping_result import (
    AGENT_PING_SCHEMA_ID, build_validated_agent_ping_result,
)
from tools.hermes_core.agent_codex_terminal_witness import load_codex_terminal_observation
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


def return_captured_text_ping(
    authority: SQLiteDelegationStore,
    captures: SQLiteAgentTerminalCaptureStore,
    results: SQLiteDelegationResultStore,
    attempt_id: str,
):
    """Return an existing result or one durable capture; never invoke a receiver."""
    if (type(authority) is not SQLiteDelegationStore
            or type(captures) is not SQLiteAgentTerminalCaptureStore
            or type(results) is not SQLiteDelegationResultStore
            or captures.authority.path != authority.path
            or results.path != authority.path):
        raise DelegationIntegrityError("ping return stores are not bound")
    receipt = authority.get_receipt(attempt_id)
    task = authority.get_delegation(receipt.delegation_id)
    if task.expected_result_schema_id != AGENT_PING_SCHEMA_ID:
        raise DelegationIntegrityError("only no-output ping return is supported")
    try:
        existing = results.get_result(attempt_id)
    except DelegationNotFoundError:
        existing = None
    if existing is not None:
        return results.record_verified_result_and_delivery(
            existing, validated_result_schema_id=AGENT_PING_SCHEMA_ID,
            delivered_at=None,
        )
    witness = load_bound_agent_start(authority, captures.start, attempt_id)
    captured = captures.get(attempt_id)
    if captured is None:
        raise DelegationIntegrityError("terminal capture is absent; outcome remains unknown")
    result = build_validated_agent_ping_result(
        witness.task, witness.lease, witness.receipt, captured.candidate,
        started_at=witness.start_result.recorded_at,
        completed_at=captured.captured_at,
    )
    return results.record_verified_result_and_delivery(
        result, validated_result_schema_id=AGENT_PING_SCHEMA_ID,
        delivered_at=None,
    )


def return_codex_ping(
    authority: SQLiteDelegationStore,
    start: SQLiteExecutionStartStore,
    registry: CodexInvocationRegistry,
    results: SQLiteDelegationResultStore,
    attempt_id: str,
):
    """Return a persisted Codex terminal ping; never invoke Codex."""
    if (type(authority) is not SQLiteDelegationStore
            or type(start) is not SQLiteExecutionStartStore
            or type(registry) is not CodexInvocationRegistry
            or type(results) is not SQLiteDelegationResultStore
            or results.path != authority.path):
        raise DelegationIntegrityError("Codex ping return stores are not bound")
    receipt = authority.get_receipt(attempt_id)
    task = authority.get_delegation(receipt.delegation_id)
    if (task.expected_result_schema_id != AGENT_PING_SCHEMA_ID
            or receipt.receiver_agent_id != "codex-cli-agent"):
        raise DelegationIntegrityError("only Codex no-output ping return is supported")
    try:
        existing = results.get_result(attempt_id)
    except DelegationNotFoundError:
        existing = None
    if existing is not None:
        return results.record_verified_result_and_delivery(
            existing, validated_result_schema_id=AGENT_PING_SCHEMA_ID,
            delivered_at=None,
        )
    witness = load_bound_agent_start(authority, start, attempt_id)
    observation = load_codex_terminal_observation(witness, registry)
    result = build_validated_agent_ping_result(
        witness.task, witness.lease, witness.receipt, observation.candidate,
        started_at=witness.start_result.recorded_at,
        completed_at=observation.completed_at,
    )
    return results.record_verified_result_and_delivery(
        result, validated_result_schema_id=AGENT_PING_SCHEMA_ID,
        delivered_at=None,
    )


def return_bound_agent_ping(
    authority: SQLiteDelegationStore,
    start: SQLiteExecutionStartStore,
    captures: SQLiteAgentTerminalCaptureStore,
    registry: CodexInvocationRegistry,
    results: SQLiteDelegationResultStore,
    attempt_id: str,
):
    """Recover one accepted agent ping from stores; never launch a receiver."""
    if (type(authority) is not SQLiteDelegationStore
            or type(start) is not SQLiteExecutionStartStore
            or type(captures) is not SQLiteAgentTerminalCaptureStore
            or type(registry) is not CodexInvocationRegistry
            or type(results) is not SQLiteDelegationResultStore
            or captures.authority.path != authority.path
            or captures.start is not start
            or results.path != authority.path):
        raise DelegationIntegrityError("agent ping recovery stores are not bound")
    receiver = authority.get_receipt(attempt_id).receiver_agent_id
    if receiver == "codex-cli-agent":
        return return_codex_ping(authority, start, registry, results, attempt_id)
    if receiver in {"kilo-cli-agent", "opencode-cli-agent"}:
        return return_captured_text_ping(authority, captures, results, attempt_id)
    raise DelegationIntegrityError("agent ping receiver is not supported")
