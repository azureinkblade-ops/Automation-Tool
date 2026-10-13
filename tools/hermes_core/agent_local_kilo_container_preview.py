"""Preview reported Kilo container stdout without certifying transport."""

from tools.hermes_core.agent_local_kilo_container_record import (
    SQLiteAgentLocalKiloContainerRecordStore,
)
from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_result_candidate import decode_agent_result_candidate
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.kilo_adapter import KiloOutputParser
from tools.hermes_core.receiver_adapter import ReceiverParseError, VerifiedResult


_MAX_STDOUT = 4 * 1024 * 1024


def preview_reported_kilo_container_ping(
    records: SQLiteAgentLocalKiloContainerRecordStore,
    attempt_id: str,
    container_id: str,
    *,
    returncode: int,
    stdout_bytes: bytes,
):
    """Validate a reported body only; do not capture, deliver, or authorize."""
    if type(records) is not SQLiteAgentLocalKiloContainerRecordStore:
        raise DelegationIntegrityError("Kilo container preview store denied")
    report = records.get(attempt_id)
    if report is None or report.container_id != container_id:
        raise DelegationIntegrityError("Kilo container preview identity mismatch")
    if (type(returncode) is not int or returncode != 0
            or type(stdout_bytes) is not bytes
            or len(stdout_bytes) > _MAX_STDOUT):
        raise DelegationIntegrityError("Kilo container preview terminal denied")
    witness = load_bound_agent_start(
        records.intents.bridge_store.authority,
        records.intents.bridge_store.start, attempt_id,
    )
    if witness.receipt.receiver_agent_id != "kilo-cli-agent":
        raise DelegationIntegrityError("Kilo container preview receiver denied")
    try:
        stdout = stdout_bytes.decode("utf-8", errors="strict")
        parsed = KiloOutputParser.parse_output(stdout)
    except UnicodeDecodeError as exc:
        raise DelegationIntegrityError("Kilo container stdout is not UTF-8") from exc
    except ReceiverParseError as exc:
        raise DelegationIntegrityError("Kilo container stdout JSONL invalid") from exc
    candidate = decode_agent_result_candidate(
        witness.bound.invocation.lineage,
        VerifiedResult(valid=parsed.get("type") == "text", payload=parsed),
    )
    validate_agent_ping_candidate(
        witness.task, witness.lease, witness.receipt, candidate,
    )
    return candidate
