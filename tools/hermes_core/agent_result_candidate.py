"""Decode structured agent text without granting result-verification authority."""

import json
from dataclasses import dataclass

from tools.hermes_core.agent_receiver_lineage import BoundAgentInvocation, BoundReceiverLineage
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.receiver_adapter import ExecutionOutcome, InvocationRecord, VerifiedResult


_RESULT_FIELDS = frozenset({
    "schema_version", "outcome", "result_payload", "output_manifest",
    "evidence_manifest", "error_code", "error_summary",
})
_TEXT_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})


@dataclass(frozen=True)
class AgentResultCandidate:
    lineage: BoundReceiverLineage
    candidate_json: str


def _reject_nonfinite(value: str):
    raise ValueError(f"non-finite JSON value: {value}")


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def decode_agent_result_candidate(
    lineage: BoundReceiverLineage, adapter_result: VerifiedResult,
) -> AgentResultCandidate:
    """Require an exact structured candidate; evidence must be verified elsewhere."""
    if type(lineage) is not BoundReceiverLineage or type(adapter_result) is not VerifiedResult:
        raise DelegationIntegrityError("agent result candidate inputs denied")
    if lineage.receiver_agent_id not in _TEXT_RECEIVERS:
        raise DelegationIntegrityError("receiver uses a different result contract")
    payload = adapter_result.payload
    if (not adapter_result.valid or type(payload) is not dict
            or payload.get("type") != "text" or type(payload.get("text")) is not str):
        raise DelegationIntegrityError("agent result is not valid terminal text")
    try:
        candidate = json.loads(
            payload["text"], parse_constant=_reject_nonfinite,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, TypeError) as exc:
        raise DelegationIntegrityError("agent result text is not strict JSON") from exc
    if (type(candidate) is not dict or set(candidate) != _RESULT_FIELDS
            or candidate["schema_version"] != "1"
            or candidate["outcome"] not in ("SUCCEEDED", "FAILED", "CANCELLED")
            or type(candidate["result_payload"]) is not dict
            or type(candidate["output_manifest"]) is not list
            or type(candidate["evidence_manifest"]) is not list
            or not all(type(item) is dict for item in candidate["output_manifest"])
            or not all(type(item) is dict for item in candidate["evidence_manifest"])):
        raise DelegationIntegrityError("agent result candidate contract mismatch")
    if candidate["outcome"] == "FAILED":
        if not all(type(candidate[key]) is str and candidate[key] for key in ("error_code", "error_summary")):
            raise DelegationIntegrityError("failed result lacks error details")
    elif candidate["error_code"] is not None or candidate["error_summary"] is not None:
        raise DelegationIntegrityError("non-failed result carries error details")
    return AgentResultCandidate(lineage=lineage, candidate_json=canonical_json(candidate))


def bind_terminal_agent_candidate(
    invocation: BoundAgentInvocation, outcome: ExecutionOutcome,
) -> AgentResultCandidate:
    """Check adapter transport identity before decoding its untrusted text."""
    if type(invocation) is not BoundAgentInvocation or type(outcome) is not ExecutionOutcome:
        raise DelegationIntegrityError("terminal candidate inputs denied")
    agent = invocation.lineage.receiver_agent_id
    terminal = {"kilo-cli-agent": "completed", "opencode-cli-agent": "TERMINAL"}.get(agent)
    record = outcome.record
    if (terminal is None or type(record) is not InvocationRecord
            or not outcome.process_started or outcome.replayed
            or record.idempotency_key != invocation.idempotency_key
            or record.runtime_run_id != invocation.runtime_run_id
            or type(record.pid) is not int or record.pid <= 0
            or record.terminal_state != terminal):
        raise DelegationIntegrityError("terminal adapter identity or state mismatch")
    return decode_agent_result_candidate(invocation.lineage, outcome.verified_result)
