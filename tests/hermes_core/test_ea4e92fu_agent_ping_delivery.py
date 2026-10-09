"""Fake-only instance-bound ping result and originator mailbox recovery."""

import pytest

from tests.hermes_core.test_ea4e92ft_agent_ping_result import materials
from tests.hermes_core.test_sqlite_delegation_result_store import make_result
from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


def accepted_authority(tmp_path, agent):
    task, lease, receipt, bound, body = materials(agent)
    authority = SQLiteDelegationStore(tmp_path / "delegations.sqlite3")
    authority.create_delegation(task)
    authority.issue_lease(lease)
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z",
    )
    authority.claim_message(
        message.message_id, recipient_agent_id=agent,
        claim_token="fake-claim", claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z",
    )
    authority.record_receipt(receipt, source_message_id=message.message_id)
    return authority, task, lease, receipt, bound, body


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_validated_synthetic_ping_returns_to_originator_once(tmp_path, agent):
    authority, task, lease, receipt, bound, body = accepted_authority(tmp_path, agent)
    candidate = AgentResultCandidate(bound, canonical_json(body))
    validated = validate_agent_ping_candidate(task, lease, receipt, candidate)
    result = make_result(
        task, lease, receipt,
        result_payload=body["result_payload"], output_manifest=[],
        evidence_manifest=body["evidence_manifest"],
    )
    store = SQLiteDelegationResultStore(authority.path)
    durable, delivery, message_id = store.record_verified_result_and_delivery(
        result, validated_result_schema_id=validated.schema_id,
        delivered_at="2026-08-27T12:05:05Z",
    )
    assert durable == result
    restarted = SQLiteDelegationStore(authority.path)
    assert restarted.get_message(message_id).recipient_agent_id == task.originator_agent_id
    assert restarted.message_body(message_id)["result"]["result_id"] == result.result_id
    replay = store.record_verified_result_and_delivery(
        result, validated_result_schema_id=validated.schema_id,
        delivered_at="2026-08-27T12:05:08Z",
    )
    assert replay == (durable, delivery, message_id)
    restarted.claim_message(
        message_id, recipient_agent_id=task.originator_agent_id,
        claim_token="originator-claim", claimed_at="2026-08-27T12:05:09Z",
        claim_expires_at="2026-08-27T12:06:00Z",
    )
    restarted.acknowledge_message(
        message_id, recipient_agent_id=task.originator_agent_id,
        claim_token="originator-claim", acknowledged_at="2026-08-27T12:05:10Z",
    )
    assert restarted.delivery_state(message_id) == "ACKNOWLEDGED"


def test_forged_ping_does_not_write_a_result(tmp_path):
    authority, task, lease, receipt, bound, body = accepted_authority(tmp_path, "kilo-cli-agent")
    body["result_payload"]["statement"] = "forged"
    candidate = AgentResultCandidate(bound, canonical_json(body))
    store = SQLiteDelegationResultStore(authority.path)
    with pytest.raises(DelegationIntegrityError):
        validate_agent_ping_candidate(task, lease, receipt, candidate)
    with pytest.raises(DelegationNotFoundError):
        store.get_result(lease.attempt_id)
