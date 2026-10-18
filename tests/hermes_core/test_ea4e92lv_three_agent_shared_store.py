"""One durable fake authority store shared by all three agent identities."""

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_result_store import make_result
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_receiver_lineage import bind_receiver_lineage
from tools.hermes_core.delegation_delivery import ReceiverMismatchError
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


AGENTS = ("codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent")


def test_three_agents_return_distinct_results_to_one_originator_after_restart(tmp_path):
    path = tmp_path / "shared-authority.sqlite3"
    authority = SQLiteDelegationStore(path)
    results = SQLiteDelegationResultStore(path)
    expected = {}
    for ordinal, agent in enumerate(AGENTS, start=1):
        task = make_envelope(
            originator_request_id=f"three-agent-request-{ordinal}",
            task_id=f"three-agent-task-{ordinal}",
            requested_target_agent_id=agent,
        )
        lease = make_lease(
            task,
            authorization_id=f"three-agent-auth-{ordinal}",
            attempt_id=f"three-agent-attempt-{ordinal}",
            route_id=f"three-agent-route-{ordinal}",
        )
        authority.create_delegation(task)
        authority.issue_lease(lease)
        message = authority.deliver_delegation(
            lease.lease_id, sender_agent_id="hermes-agent-router",
            delivered_at="2026-08-27T12:05:00Z")
        wrong_agent = AGENTS[ordinal % len(AGENTS)]
        with pytest.raises(ReceiverMismatchError):
            authority.claim_message(
                message.message_id, recipient_agent_id=wrong_agent,
                claim_token="wrong-agent-claim",
                claimed_at="2026-08-27T12:05:00Z",
                claim_expires_at="2026-08-27T12:06:00Z")
        authority.claim_message(
            message.message_id, recipient_agent_id=agent,
            claim_token=f"three-agent-claim-{ordinal}",
            claimed_at="2026-08-27T12:05:00Z",
            claim_expires_at="2026-08-27T12:06:00Z")
        receipt = make_receipt(
            task, lease,
            launch_attempt_id=f"three-agent-launch-{ordinal}",
            runtime_run_id=f"three-agent-runtime-{ordinal}",
        )
        authority.record_receipt(receipt, source_message_id=message.message_id)
        bound = bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)
        result = make_result(task, lease, receipt)
        _, delivery, result_message_id = results.record_verified_result_and_delivery(
            result, validated_result_schema_id=bound.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:05Z")
        assert results.record_verified_result_and_delivery(
            result, validated_result_schema_id=bound.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:08Z") == (result, delivery, result_message_id)
        expected[result_message_id] = (task, result, agent)

    restarted = SQLiteDelegationStore(path)
    mailbox = restarted.list_mailbox("hermes-originator")
    assert {message.message_id for message in mailbox} == set(expected)
    assert len(mailbox) == len(AGENTS)
    for message_id, (task, result, agent) in expected.items():
        message = restarted.get_message(message_id)
        assert message.recipient_agent_id == task.originator_agent_id
        assert restarted.message_body(message_id)["result"]["result_id"] == result.result_id
        assert result.receiver_agent_id == agent
        claim_token = f"originator-{agent}"
        restarted.claim_message(
            message_id, recipient_agent_id=task.originator_agent_id,
            claim_token=claim_token, claimed_at="2026-08-27T12:05:09Z",
            claim_expires_at="2026-08-27T12:06:00Z")
        restarted.acknowledge_message(
            message_id, recipient_agent_id=task.originator_agent_id,
            claim_token=claim_token, acknowledged_at="2026-08-27T12:05:10Z")
        assert restarted.delivery_state(message_id) == "ACKNOWLEDGED"
