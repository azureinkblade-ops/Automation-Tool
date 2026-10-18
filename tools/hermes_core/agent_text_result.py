"""Bounded inline text result contract for a delegated agent."""

import json

from tools.hermes_core.agent_receiver_lineage import BoundReceiverLineage, bind_receiver_lineage
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.delegation_result import build_delegation_result
from tools.hermes_core.hashing import canonical_json, sha256_payload


AGENT_TEXT_SCHEMA_ID = "hermes.agent_text_result/v1"
MAX_TEXT_BYTES = 4096
EXPECTED_EVIDENCE = ({
    "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
},)
AGENT_TEXT_SCHEMA_HASH = sha256_payload({
    "schema_id": AGENT_TEXT_SCHEMA_ID,
    "schema_version": "1",
    "outcome": "SUCCEEDED",
    "result_payload_fields": ["task_input_hash", "receiver_receipt_hash", "text"],
    "max_text_bytes": MAX_TEXT_BYTES,
    "output_manifest": "empty",
    "evidence_type": "receiver_acceptance_sha256",
})


def _reject_nonfinite(value):
    raise ValueError(f"non-finite JSON value: {value}")


def validate_agent_text_candidate(envelope, lease, receipt, candidate):
    """Check byte-bound lineage and shape, not the truth of an agent's text."""
    if (type(candidate) is not AgentResultCandidate
            or type(candidate.lineage) is not BoundReceiverLineage
            or type(candidate.candidate_json) is not str):
        raise DelegationIntegrityError("agent text candidate denied")
    bound = bind_receiver_lineage(
        envelope, lease, receipt,
        receiver_agent_id=candidate.lineage.receiver_agent_id,
    )
    if (candidate.lineage != bound
            or envelope.expected_result_schema_id != AGENT_TEXT_SCHEMA_ID
            or lease.expected_result_schema_id != AGENT_TEXT_SCHEMA_ID
            or tuple(envelope.expected_evidence) != EXPECTED_EVIDENCE
            or tuple(lease.expected_evidence) != EXPECTED_EVIDENCE):
        raise DelegationIntegrityError("agent text lineage or schema mismatch")
    try:
        body = json.loads(candidate.candidate_json, parse_constant=_reject_nonfinite)
    except (TypeError, ValueError) as exc:
        raise DelegationIntegrityError("agent text candidate is not JSON") from exc
    if (type(body) is not dict or canonical_json(body) != candidate.candidate_json
            or set(body) != {
                "schema_version", "outcome", "result_payload", "output_manifest",
                "evidence_manifest", "error_code", "error_summary",
            }
            or body["schema_version"] != "1" or body["outcome"] != "SUCCEEDED"
            or body["output_manifest"] != []
            or body["error_code"] is not None or body["error_summary"] is not None):
        raise DelegationIntegrityError("agent text body mismatch")
    payload = body["result_payload"]
    if (type(payload) is not dict
            or set(payload) != {"task_input_hash", "receiver_receipt_hash", "text"}
            or payload["task_input_hash"] != envelope.task_input_hash
            or payload["receiver_receipt_hash"] != receipt.artifact_hash
            or type(payload["text"]) is not str
            or not payload["text"].strip()):
        raise DelegationIntegrityError("agent text payload mismatch")
    try:
        text_bytes = payload["text"].encode("utf-8")
    except UnicodeError as exc:
        raise DelegationIntegrityError("agent text encoding invalid") from exc
    if len(text_bytes) > MAX_TEXT_BYTES:
        raise DelegationIntegrityError("agent text exceeds byte limit")
    evidence = body["evidence_manifest"]
    if (type(evidence) is not list or len(evidence) != 1
            or type(evidence[0]) is not dict
            or type(evidence[0].get("ordinal")) is not int
            or evidence[0] != {
                "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
                "sha256": receipt.artifact_hash,
            }):
        raise DelegationIntegrityError("agent text receipt evidence mismatch")
    return sha256_payload(body)


def build_validated_agent_text_result(
    envelope, lease, receipt, candidate, *, started_at, completed_at,
):
    """Build a canonical result after pure schema validation."""
    validate_agent_text_candidate(envelope, lease, receipt, candidate)
    body = json.loads(candidate.candidate_json)
    return build_delegation_result(
        delegation_id=envelope.delegation_id,
        delegated_task_hash=envelope.artifact_hash,
        authorization_id=lease.authorization_id,
        authorization_hash=lease.authorization_hash,
        attempt_id=lease.attempt_id,
        attempt_hash=lease.attempt_hash,
        launch_attempt_id=receipt.launch_attempt_id,
        launch_attempt_hash=receipt.launch_attempt_hash,
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.artifact_hash,
        receiver_agent_id=receipt.receiver_agent_id,
        receiver_descriptor_hash=receipt.receiver_descriptor_hash,
        runtime_run_id=receipt.runtime_run_id,
        outcome=body["outcome"],
        result_payload=body["result_payload"],
        output_manifest=body["output_manifest"],
        evidence_manifest=body["evidence_manifest"],
        started_at=started_at,
        completed_at=completed_at,
        error_code=body["error_code"],
        error_summary=body["error_summary"],
    )
