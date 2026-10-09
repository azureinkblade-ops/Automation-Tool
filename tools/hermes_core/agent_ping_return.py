"""Recover a captured text-agent ping and return it to the originator once."""

from tools.hermes_core.agent_ping_result import (
    AGENT_PING_SCHEMA_ID, build_validated_agent_ping_result,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


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
