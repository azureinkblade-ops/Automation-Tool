"""Parse reported text-process bytes without certifying process provenance."""

from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_result_candidate import (
    AgentResultCandidate, decode_agent_result_candidate,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_process_observation import (
    SQLiteAgentTextProcessObservationStore,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.receiver_adapter import ReceiverParseError, VerifiedResult


def preview_reported_text_ping_candidate(
    observations: SQLiteAgentTextProcessObservationStore,
    attempt_id: str,
) -> AgentResultCandidate:
    """Check reported bytes against the ping schema; never persist a result."""
    if type(observations) is not SQLiteAgentTextProcessObservationStore:
        raise DelegationIntegrityError("text process observation store denied")
    terminal = observations.get_terminal(attempt_id)
    if terminal is None or terminal.returncode != 0:
        raise DelegationIntegrityError("successful text process terminal absent")
    witness = load_bound_agent_start(
        observations.intents.bridge_store.authority,
        observations.intents.bridge_store.start,
        attempt_id,
    )
    receiver = witness.receipt.receiver_agent_id
    try:
        stdout = terminal.stdout_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DelegationIntegrityError("text process stdout is not UTF-8") from exc
    if receiver == "kilo-cli-agent":
        from tools.hermes_core.kilo_adapter import KiloOutputParser

        parse = KiloOutputParser.parse_output
    elif receiver == "opencode-cli-agent":
        from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter

        parse = OpenCodeReceiverAdapter().parse_output
    else:
        raise DelegationIntegrityError("text process receiver denied")
    try:
        parsed = parse(stdout)
    except ReceiverParseError as exc:
        raise DelegationIntegrityError("text process JSONL invalid") from exc
    candidate = decode_agent_result_candidate(
        witness.bound.invocation.lineage,
        VerifiedResult(valid=parsed.get("type") == "text", payload=parsed),
    )
    validate_agent_ping_candidate(
        witness.task, witness.lease, witness.receipt, candidate,
    )
    return candidate
