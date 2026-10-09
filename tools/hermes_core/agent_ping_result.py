"""Pure instance-bound schema check for a no-output agent qualification ping."""

import json
from dataclasses import dataclass

from tools.hermes_core.agent_receiver_lineage import BoundReceiverLineage, bind_receiver_lineage
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.delegated_task import (
    DelegatedCapabilityLease, DelegatedTaskEnvelope, DelegationIntegrityError,
)
from tools.hermes_core.delegation_delivery import DelegationReceipt
from tools.hermes_core.hashing import canonical_json, sha256_payload


AGENT_PING_SCHEMA_ID = "hermes.agent_ping_result/v1"
_SCHEMA_MATERIAL = {
    "schema_id": AGENT_PING_SCHEMA_ID,
    "schema_version": "1",
    "outcome": "SUCCEEDED",
    "result_payload_fields": ["task_input_hash", "receiver_receipt_hash", "statement"],
    "output_manifest": "empty",
    "evidence_type": "receiver_acceptance_sha256",
}
AGENT_PING_SCHEMA_HASH = sha256_payload(_SCHEMA_MATERIAL)


@dataclass(frozen=True)
class AgentPingValidation:
    schema_id: str
    schema_hash: str
    candidate_hash: str
    receipt_hash: str


def _reject_constant(value):
    raise ValueError(f"non-finite JSON value: {value}")


def validate_agent_ping_candidate(
    envelope: DelegatedTaskEnvelope,
    lease: DelegatedCapabilityLease,
    receipt: DelegationReceipt,
    candidate: AgentResultCandidate,
) -> AgentPingValidation:
    """Validate a bound ping body, not transport or production authority."""
    if (type(candidate) is not AgentResultCandidate
            or type(candidate.lineage) is not BoundReceiverLineage
            or type(candidate.candidate_json) is not str):
        raise DelegationIntegrityError("agent ping candidate denied")
    bound = bind_receiver_lineage(
        envelope, lease, receipt,
        receiver_agent_id=candidate.lineage.receiver_agent_id,
    )
    if (candidate.lineage != bound
            or envelope.expected_result_schema_id != AGENT_PING_SCHEMA_ID
            or lease.expected_result_schema_id != AGENT_PING_SCHEMA_ID
            or tuple(envelope.expected_evidence) != ({
                "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            },)
            or tuple(lease.expected_evidence) != tuple(envelope.expected_evidence)):
        raise DelegationIntegrityError("agent ping lineage or schema mismatch")
    try:
        body = json.loads(candidate.candidate_json, parse_constant=_reject_constant)
    except (TypeError, ValueError) as exc:
        raise DelegationIntegrityError("agent ping candidate is not JSON") from exc
    if (type(body) is not dict or canonical_json(body) != candidate.candidate_json
            or set(body) != {
                "schema_version", "outcome", "result_payload", "output_manifest",
                "evidence_manifest", "error_code", "error_summary",
            }
            or body["schema_version"] != "1" or body["outcome"] != "SUCCEEDED"
            or body["output_manifest"] != []
            or body["error_code"] is not None or body["error_summary"] is not None):
        raise DelegationIntegrityError("agent ping body mismatch")
    payload = body["result_payload"]
    if (type(payload) is not dict
            or set(payload) != {"task_input_hash", "receiver_receipt_hash", "statement"}
            or payload["task_input_hash"] != envelope.task_input_hash
            or payload["receiver_receipt_hash"] != receipt.artifact_hash
            or payload["statement"] != f"{bound.receiver_agent_id}:PING_OK"):
        raise DelegationIntegrityError("agent ping payload is not instance-bound")
    evidence = body["evidence_manifest"]
    if (type(evidence) is not list or len(evidence) != 1
            or type(evidence[0]) is not dict
            or set(evidence[0]) != {"ordinal", "evidence_type", "sha256"}
            or type(evidence[0]["ordinal"]) is not int
            or evidence[0] != {
                "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
                "sha256": receipt.artifact_hash,
            }):
        raise DelegationIntegrityError("agent ping receipt evidence mismatch")
    return AgentPingValidation(
        schema_id=AGENT_PING_SCHEMA_ID,
        schema_hash=AGENT_PING_SCHEMA_HASH,
        candidate_hash=sha256_payload(body),
        receipt_hash=receipt.artifact_hash,
    )
