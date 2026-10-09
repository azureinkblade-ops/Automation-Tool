"""Instance-bound ping schema checks using fake canonical artifacts only."""

import json
from dataclasses import replace

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_ping_result import (
    AGENT_PING_SCHEMA_HASH, AGENT_PING_SCHEMA_ID, validate_agent_ping_candidate,
)
from tools.hermes_core.agent_receiver_lineage import bind_receiver_lineage
from tools.hermes_core.agent_result_candidate import (
    AgentResultCandidate, decode_agent_result_candidate,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.receiver_adapter import VerifiedResult


EXPECTED_EVIDENCE = [{"ordinal": 0, "evidence_type": "receiver_acceptance_sha256"}]


def materials(agent):
    task = make_envelope(
        requested_target_agent_id=agent,
        expected_result_schema_id=AGENT_PING_SCHEMA_ID,
        expected_evidence=EXPECTED_EVIDENCE,
    )
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    bound = bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)
    body = {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": task.task_input_hash,
            "receiver_receipt_hash": receipt.artifact_hash,
            "statement": f"{agent}:PING_OK",
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            "sha256": receipt.artifact_hash,
        }],
        "error_code": None, "error_summary": None,
    }
    return task, lease, receipt, bound, body


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_all_three_agents_validate_same_committed_ping_schema(agent):
    task, lease, receipt, bound, body = materials(agent)
    if agent == "codex-cli-agent":
        candidate = AgentResultCandidate(bound, canonical_json(body))
    else:
        candidate = decode_agent_result_candidate(
            bound, VerifiedResult(valid=True, payload={"type": "text", "text": json.dumps(body)}),
        )
    validation = validate_agent_ping_candidate(task, lease, receipt, candidate)
    assert validation.schema_id == AGENT_PING_SCHEMA_ID
    assert validation.schema_hash == AGENT_PING_SCHEMA_HASH
    assert validation.receipt_hash == receipt.artifact_hash


@pytest.mark.parametrize("change", [
    lambda body: body["result_payload"].update(statement="wrong"),
    lambda body: body["result_payload"].update(task_input_hash="a" * 64),
    lambda body: body["result_payload"].update(receiver_receipt_hash="b" * 64),
    lambda body: body["evidence_manifest"][0].update(sha256="c" * 64),
    lambda body: body.update(output_manifest=[{"reference": "forged"}]),
    lambda body: body.update(outcome="FAILED"),
    lambda body: body.update(schema_version="2"),
])
def test_ping_claim_mismatch_is_denied(change):
    task, lease, receipt, bound, body = materials("kilo-cli-agent")
    change(body)
    candidate = AgentResultCandidate(bound, canonical_json(body))
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(task, lease, receipt, candidate)


def test_wrong_delegated_schema_and_receiver_lineage_are_denied():
    task, lease, receipt, bound, body = materials("opencode-cli-agent")
    candidate = AgentResultCandidate(bound, canonical_json(body))
    wrong_task = make_envelope(requested_target_agent_id="opencode-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(wrong_task, lease, receipt, candidate)
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(
            task, lease, receipt,
            replace(candidate, lineage=replace(bound, receiver_agent_id="kilo-cli-agent")),
        )


def test_duplicate_or_nonfinite_forged_candidate_is_denied():
    task, lease, receipt, bound, body = materials("kilo-cli-agent")
    forged = canonical_json(body).replace('"schema_version":"1"',
        '"schema_version":"1","schema_version":"1"')
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(task, lease, receipt, AgentResultCandidate(bound, forged))
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(task, lease, receipt, AgentResultCandidate(bound, "NaN"))


def test_invalid_candidate_lineage_type_is_denied():
    task, lease, receipt, _, body = materials("kilo-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(
            task, lease, receipt, AgentResultCandidate(None, canonical_json(body)),
        )
