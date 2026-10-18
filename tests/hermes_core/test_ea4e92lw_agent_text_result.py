"""Fake-only bounded text handoff; no receiver or model is launched."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_receiver_lineage import bind_receiver_lineage
from tools.hermes_core.agent_result_candidate import AgentResultCandidate
from tools.hermes_core.agent_text_result import (
    AGENT_TEXT_SCHEMA_HASH, AGENT_TEXT_SCHEMA_ID, MAX_TEXT_BYTES,
    build_validated_agent_text_result, validate_agent_text_candidate,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.delegation_result import build_delegation_result
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore


AGENTS = ("codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent")
EVIDENCE = [{"ordinal": 0, "evidence_type": "receiver_acceptance_sha256"}]
DELIVERY_TIME = datetime(2026, 8, 27, 12, 5, 5, tzinfo=timezone.utc)


def materials(agent, text="A bounded reply"):
    task = make_envelope(
        requested_target_agent_id=agent,
        expected_result_schema_id=AGENT_TEXT_SCHEMA_ID,
        expected_evidence=EVIDENCE,
    )
    lease = make_lease(task)
    receipt = make_receipt(task, lease)
    bound = bind_receiver_lineage(task, lease, receipt, receiver_agent_id=agent)
    body = {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {
            "task_input_hash": task.task_input_hash,
            "receiver_receipt_hash": receipt.artifact_hash,
            "text": text,
        },
        "output_manifest": [],
        "evidence_manifest": [{
            "ordinal": 0, "evidence_type": "receiver_acceptance_sha256",
            "sha256": receipt.artifact_hash,
        }],
        "error_code": None, "error_summary": None,
    }
    return task, lease, receipt, bound, body


@pytest.mark.parametrize("agent", AGENTS)
def test_text_result_delivers_once_to_originator_after_restart(tmp_path, agent):
    task, lease, receipt, bound, body = materials(agent)
    candidate = AgentResultCandidate(bound, canonical_json(body))
    assert len(AGENT_TEXT_SCHEMA_HASH) == 64
    assert validate_agent_text_candidate(task, lease, receipt, candidate)
    result = build_validated_agent_text_result(
        task, lease, receipt, candidate,
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    authority = SQLiteDelegationStore(tmp_path / "authority.sqlite3")
    authority.create_delegation(task)
    authority.issue_lease(lease)
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z",
    )
    authority.claim_message(
        message.message_id, recipient_agent_id=agent, claim_token="fake-claim",
        claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z",
    )
    authority.record_receipt(receipt, source_message_id=message.message_id)
    results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
    first = results.record_verified_result_and_delivery(
        result, validated_result_schema_id=AGENT_TEXT_SCHEMA_ID,
        delivered_at="2026-08-27T12:05:05Z",
    )
    assert results.record_verified_result_and_delivery(
        result, validated_result_schema_id=AGENT_TEXT_SCHEMA_ID,
        delivered_at="2026-08-27T12:05:08Z",
    ) == first
    restarted = SQLiteDelegationStore(authority.path)
    assert len(restarted.list_mailbox(task.originator_agent_id)) == 1
    assert restarted.message_body(first[2])["result"]["result_payload"]["text"] == "A bounded reply"


@pytest.mark.parametrize("mutation", [
    lambda body: body["result_payload"].update(task_input_hash="a" * 64),
    lambda body: body["result_payload"].update(receiver_receipt_hash="b" * 64),
    lambda body: body["result_payload"].update(text=" "),
    lambda body: body["result_payload"].update(text="\u00e9" * (MAX_TEXT_BYTES // 2 + 1)),
    lambda body: body["result_payload"].update(text="\ud800"),
    lambda body: body["evidence_manifest"][0].update(sha256="c" * 64),
    lambda body: body.update(outcome="FAILED"),
    lambda body: body.update(output_manifest=[{"reference": "unverified"}]),
    lambda body: body.update(schema_version="2"),
])
def test_divergent_text_claim_is_denied(mutation):
    task, lease, receipt, bound, body = materials("kilo-cli-agent")
    mutation(body)
    with pytest.raises(DelegationIntegrityError):
        validate_agent_text_candidate(
            task, lease, receipt, AgentResultCandidate(bound, canonical_json(body)),
        )


def test_receiver_or_schema_substitution_is_denied():
    task, lease, receipt, bound, body = materials("opencode-cli-agent")
    candidate = AgentResultCandidate(bound, canonical_json(body))
    with pytest.raises(DelegationIntegrityError):
        validate_agent_text_candidate(
            task, lease, receipt,
            replace(candidate, lineage=replace(bound, receiver_agent_id="kilo-cli-agent")),
        )
    wrong_task = make_envelope(requested_target_agent_id="opencode-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        validate_agent_text_candidate(wrong_task, lease, receipt, candidate)


def test_duplicate_json_field_is_denied():
    task, lease, receipt, bound, body = materials("codex-cli-agent")
    forged = canonical_json(deepcopy(body)).replace(
        '"schema_version":"1"', '"schema_version":"1","schema_version":"1"',
    )
    with pytest.raises(DelegationIntegrityError):
        validate_agent_text_candidate(
            task, lease, receipt, AgentResultCandidate(bound, forged),
        )


def test_store_rejects_self_declared_text_schema_without_matching_payload(tmp_path):
    task, lease, receipt, bound, body = materials("kilo-cli-agent")
    result = build_validated_agent_text_result(
        task, lease, receipt, AgentResultCandidate(bound, canonical_json(body)),
        started_at="2026-08-27T12:05:03Z",
        completed_at="2026-08-27T12:05:04Z",
    )
    bad_payload = dict(result.result_payload, task_input_hash="a" * 64)
    forged = build_delegation_result(**{
        **result.to_canonical_dict(), "result_payload": bad_payload,
    })
    authority = SQLiteDelegationStore(tmp_path / "authority.sqlite3")
    authority.create_delegation(task)
    authority.issue_lease(lease)
    message = authority.deliver_delegation(
        lease.lease_id, sender_agent_id="hermes-agent-router",
        delivered_at="2026-08-27T12:05:00Z",
    )
    authority.claim_message(
        message.message_id, recipient_agent_id="kilo-cli-agent",
        claim_token="fake-claim", claimed_at="2026-08-27T12:05:00Z",
        claim_expires_at="2026-08-27T12:06:00Z",
    )
    authority.record_receipt(receipt, source_message_id=message.message_id)
    store = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
    with pytest.raises(DelegationIntegrityError, match="text result contract"):
        store.record_verified_result_and_delivery(
            forged, validated_result_schema_id=AGENT_TEXT_SCHEMA_ID,
            delivered_at=None,
        )
    assert authority.list_mailbox(task.originator_agent_id) == []
