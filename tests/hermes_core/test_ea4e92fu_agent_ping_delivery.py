"""Fake-only instance-bound ping result and originator mailbox recovery."""

from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_ea4e92ft_agent_ping_result import materials
from tests.hermes_core.test_sqlite_delegation_result_store import make_result
from tools.hermes_core.agent_ping_result import build_validated_agent_ping_result
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


def ping_store(path, at="2026-08-27T12:05:05Z"):
    instant = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return SQLiteDelegationResultStore(path, clock=lambda: instant)


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
    result = build_validated_agent_ping_result(
        task, lease, receipt, candidate,
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    store = ping_store(authority.path)
    durable, delivery, message_id = store.record_verified_result_and_delivery(
        result, validated_result_schema_id=task.expected_result_schema_id,
        delivered_at="2026-08-27T12:05:05Z",
    )
    assert durable == result
    restarted = SQLiteDelegationStore(authority.path)
    assert restarted.get_message(message_id).recipient_agent_id == task.originator_agent_id
    assert restarted.message_body(message_id)["result"]["result_id"] == result.result_id
    replay = store.record_verified_result_and_delivery(
        result, validated_result_schema_id=task.expected_result_schema_id,
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
    store = ping_store(authority.path)
    with pytest.raises(DelegationIntegrityError):
        build_validated_agent_ping_result(
            task, lease, receipt, candidate,
            started_at="2026-08-27T12:05:03Z",
            completed_at="2026-08-27T12:05:04Z",
        )
    with pytest.raises(DelegationNotFoundError):
        store.get_result(lease.attempt_id)


@pytest.mark.parametrize("forgery", [
    "payload", "receipt", "extra_payload", "evidence", "output",
])
def test_self_declared_ping_schema_cannot_store_forged_result(tmp_path, forgery):
    authority, task, lease, receipt, _, body = accepted_authority(
        tmp_path, "kilo-cli-agent",
    )
    payload = dict(body["result_payload"])
    evidence = [dict(body["evidence_manifest"][0])]
    outputs = []
    if forgery == "payload":
        payload["statement"] = "forged"
    elif forgery == "receipt":
        payload["receiver_receipt_hash"] = "f" * 64
    elif forgery == "extra_payload":
        payload["unapproved"] = True
    elif forgery == "evidence":
        evidence[0]["sha256"] = "f" * 64
    else:
        outputs = [{
            "ordinal": 0, "reference_type": "workspace_file",
            "reference": "outputs/report.json", "sha256": "f" * 64,
            "media_type": "application/json",
        }]
    result = make_result(
        task, lease, receipt, result_payload=payload,
        output_manifest=outputs, evidence_manifest=evidence,
    )
    store = ping_store(authority.path)
    with pytest.raises(DelegationIntegrityError):
        store.record_verified_result_and_delivery(
            result, validated_result_schema_id=task.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:05Z",
        )
    with pytest.raises(DelegationNotFoundError):
        store.get_result(lease.attempt_id)


@pytest.mark.parametrize("at,allowed", [
    ("2026-08-27T11:59:59Z", False),
    ("2026-08-27T12:00:00Z", False),
    ("2026-08-27T12:05:05Z", True),
    ("2026-08-27T12:10:00Z", False),
    ("2026-08-27T12:10:01Z", False),
])
def test_new_ping_success_uses_store_clock_at_lease_boundary(tmp_path, at, allowed):
    authority, task, lease, receipt, bound, body = accepted_authority(
        tmp_path, "codex-cli-agent",
    )
    candidate = AgentResultCandidate(bound, canonical_json(body))
    result = build_validated_agent_ping_result(
        task, lease, receipt, candidate,
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    store = ping_store(authority.path, at=at)
    if allowed:
        store.record_verified_result_and_delivery(
            result, validated_result_schema_id=task.expected_result_schema_id,
            delivered_at="2026-08-27T12:05:05Z",
        )
    else:
        with pytest.raises(DelegationIntegrityError):
            store.record_verified_result_and_delivery(
                result, validated_result_schema_id=task.expected_result_schema_id,
                delivered_at="2026-08-27T12:05:05Z",
            )
        with pytest.raises(DelegationNotFoundError):
            store.get_result(lease.attempt_id)
        assert authority.list_mailbox(task.originator_agent_id) == []


def test_exact_ping_replay_after_expiry_does_not_send_again(tmp_path):
    authority, task, lease, receipt, bound, body = accepted_authority(
        tmp_path, "kilo-cli-agent",
    )
    result = build_validated_agent_ping_result(
        task, lease, receipt, AgentResultCandidate(bound, canonical_json(body)),
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    first = ping_store(authority.path).record_verified_result_and_delivery(
        result, validated_result_schema_id=task.expected_result_schema_id,
        delivered_at="2026-08-27T12:05:05Z",
    )
    replay = ping_store(authority.path, at="2026-08-27T12:10:01Z")
    assert replay.record_verified_result_and_delivery(
        result, validated_result_schema_id=task.expected_result_schema_id,
        delivered_at="2026-08-27T12:10:01Z",
    ) == first
    assert len(authority.list_mailbox(task.originator_agent_id)) == 1


def test_new_ping_delivery_uses_store_transaction_time_when_unsupplied(tmp_path):
    authority, task, lease, receipt, bound, body = accepted_authority(
        tmp_path, "kilo-cli-agent",
    )
    result = build_validated_agent_ping_result(
        task, lease, receipt, AgentResultCandidate(bound, canonical_json(body)),
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    _, delivery, message_id = ping_store(authority.path).record_verified_result_and_delivery(
        result, validated_result_schema_id=task.expected_result_schema_id,
        delivered_at=None,
    )
    assert delivery.created_at == "2026-08-27T12:05:05Z"
    assert authority.get_message(message_id).created_at == delivery.created_at


@pytest.mark.parametrize("clock,delivered_at", [
    (lambda: datetime(2026, 8, 27, 12, 5, 5), "2026-08-27T12:05:05Z"),
    (lambda: datetime(2026, 8, 27, 12, 5, 5, tzinfo=timezone.utc),
     "2026-08-27T12:05:06Z"),
])
def test_ping_new_success_rejects_invalid_clock_or_claimed_delivery_time(
    tmp_path, clock, delivered_at,
):
    authority, task, lease, receipt, bound, body = accepted_authority(
        tmp_path, "opencode-cli-agent",
    )
    result = build_validated_agent_ping_result(
        task, lease, receipt, AgentResultCandidate(bound, canonical_json(body)),
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    store = SQLiteDelegationResultStore(authority.path, clock=clock)
    with pytest.raises(DelegationIntegrityError):
        store.record_verified_result_and_delivery(
            result, validated_result_schema_id=task.expected_result_schema_id,
            delivered_at=delivered_at,
        )
    with pytest.raises(DelegationNotFoundError):
        store.get_result(lease.attempt_id)
    assert authority.list_mailbox(task.originator_agent_id) == []
