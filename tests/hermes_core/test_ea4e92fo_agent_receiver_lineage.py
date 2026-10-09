"""Pure Codex/Kilo/OpenCode receiver-lineage checks; no agent invocation."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_result_store import make_result
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_receiver_lineage import bind_receiver_lineage
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_all_three_agents_bind_existing_canonical_lineage(agent):
    task = make_envelope(requested_target_agent_id=agent)
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    bound = bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)
    assert bound.delegation_id == task.delegation_id
    assert bound.attempt_id == lease.attempt_id
    assert bound.launch_attempt_id == receipt.launch_attempt_id
    assert bound.task_input_hash == task.task_input_hash


@pytest.mark.parametrize("change", [
    lambda t, l, r: (t, l, replace(r, receiver_agent_id="opencode-cli-agent")),
    lambda t, l, r: (t, l, replace(r, attempt_id="another-attempt")),
    lambda t, l, r: (t, l, replace(r, delegation_id="another-delegation")),
    lambda t, l, r: (t, l, replace(r, capability_lease_hash="0" * 64)),
    lambda t, l, r: (t, replace(l, expected_result_schema_id="other-schema"), r),
    lambda t, l, r: (t, l, make_receipt(t, l, outcome="REJECTED",
                                      reason_code="WRONG_RECEIVER",
                                      reason_summary="Not this agent.")),
])
def test_divergent_or_rejected_lineage_fails_closed(change):
    task = make_envelope(requested_target_agent_id="kilo-cli-agent")
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    task, lease, receipt = change(task, lease, receipt)
    with pytest.raises(DelegationIntegrityError):
        bind_receiver_lineage(task, lease, receipt, receiver_agent_id="kilo-cli-agent")


def test_wrong_caller_receiver_and_tampered_task_fail_closed():
    task = make_envelope(requested_target_agent_id="opencode-cli-agent")
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    with pytest.raises(DelegationIntegrityError):
        bind_receiver_lineage(task, lease, receipt, receiver_agent_id="kilo-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        bind_receiver_lineage(replace(task, objective="changed"), lease,
                              receipt, receiver_agent_id="opencode-cli-agent")


@pytest.mark.parametrize("agent", [None, ["kilo-cli-agent"]])
def test_invalid_receiver_id_type_fails_closed(agent):
    task = make_envelope(requested_target_agent_id="kilo-cli-agent")
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    with pytest.raises(DelegationIntegrityError):
        bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)


@pytest.mark.parametrize("agent", [
    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
])
def test_verified_synthetic_result_returns_to_originator_after_restart(tmp_path, agent):
    authority = SQLiteDelegationStore(tmp_path / "delegations.sqlite3")
    task = make_envelope(requested_target_agent_id=agent)
    lease = make_lease(task)
    authority.create_delegation(task)
    authority.issue_lease(lease)
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z")
    authority.claim_message(
        message.message_id, recipient_agent_id=agent,
        claim_token="fake-receiver-claim", claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z")
    receipt = make_receipt(task, lease)
    authority.record_receipt(receipt, source_message_id=message.message_id)
    bound = bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)
    result = make_result(task, lease, receipt)
    assert result.attempt_id == bound.attempt_id
    result_store = SQLiteDelegationResultStore(authority.path)
    _, delivery, result_message_id = result_store.record_verified_result_and_delivery(
        result, validated_result_schema_id=bound.expected_result_schema_id,
        delivered_at="2026-08-27T12:05:05Z")
    restarted = SQLiteDelegationStore(authority.path)
    assert restarted.get_message(result_message_id).recipient_agent_id == task.originator_agent_id
    assert restarted.message_body(result_message_id)["result"]["result_id"] == result.result_id
    restarted.claim_message(
        result_message_id, recipient_agent_id=task.originator_agent_id,
        claim_token="originator-claim", claimed_at="2026-08-27T12:05:06Z",
        claim_expires_at="2026-08-27T12:06:00Z")
    restarted.acknowledge_message(
        result_message_id, recipient_agent_id=task.originator_agent_id,
        claim_token="originator-claim", acknowledged_at="2026-08-27T12:05:07Z")
    assert restarted.delivery_state(result_message_id) == "ACKNOWLEDGED"
    assert result_store.get_delivery(delivery.result_delivery_id) == delivery


def test_cross_agent_result_cannot_claim_other_receivers_attempt(tmp_path):
    authority = SQLiteDelegationStore(tmp_path / "delegations.sqlite3")
    task = make_envelope(requested_target_agent_id="kilo-cli-agent")
    lease = make_lease(task)
    authority.create_delegation(task)
    authority.issue_lease(lease)
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z")
    authority.claim_message(
        message.message_id, recipient_agent_id="kilo-cli-agent",
        claim_token="fake-receiver-claim", claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z")
    receipt = make_receipt(task, lease)
    authority.record_receipt(receipt, source_message_id=message.message_id)
    forged = make_result(task, lease, receipt,
                         receiver_agent_id="opencode-cli-agent")
    result_store = SQLiteDelegationResultStore(authority.path)
    with pytest.raises(DelegationIntegrityError):
        result_store.record_verified_result_and_delivery(
            forged, validated_result_schema_id=task.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:05Z")
