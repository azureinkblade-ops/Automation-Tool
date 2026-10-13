"""Pure attempt-bound fake ping body; not a gateway or receiver response."""

import hashlib
import json

from tools.hermes_core.agent_result_candidate import decode_agent_result_candidate
from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.agent_text_ping_command import build_agent_text_ping_message
from tools.hermes_core.agent_invocation_bridge import AgentInvocationBridge
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.receiver_adapter import VerifiedResult


def build_agent_local_kilo_fake_ping_body(
    witness: DurableAgentStart, bridge: AgentInvocationBridge,
) -> dict:
    """Produce validated result text and a bounded illustrative SSE body."""
    receiver, _ = build_agent_text_ping_message(witness, bridge)
    if receiver != "kilo-cli-agent":
        raise DelegationIntegrityError("fake Kilo ping body received another agent")
    body = {
        "schema_version": "1",
        "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": witness.task.task_input_hash,
            "receiver_receipt_hash": witness.receipt.artifact_hash,
            "statement": "kilo-cli-agent:PING_OK",
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0,
            "evidence_type": "receiver_acceptance_sha256",
            "sha256": witness.receipt.artifact_hash,
        }],
        "error_code": None,
        "error_summary": None,
    }
    text = canonical_json(body)
    candidate = decode_agent_result_candidate(
        witness.bound.invocation.lineage,
        VerifiedResult(valid=True, payload={"type": "text", "text": text}),
    )
    validate_agent_ping_candidate(
        witness.task, witness.lease, witness.receipt, candidate,
    )
    event = json.dumps(
        {"choices": [{"delta": {"content": text}}]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    sse = f"data: {event}\n\ndata: [DONE]\n\n".encode("ascii")
    if len(sse) > 65536:
        raise DelegationIntegrityError("fake Kilo ping body exceeds bound")
    return {
        "schema_id": "hermes.agent-local-kilo-fake-ping-body/v1",
        "attempt_id": witness.lease.attempt_id,
        "candidate_json": text,
        "sse_bytes": sse,
        "sse_sha256": hashlib.sha256(sse).hexdigest(),
        "gateway_qualified": False,
        "receiver_executed": False,
        "model_invoked": False,
        "launch_authorized": False,
    }
