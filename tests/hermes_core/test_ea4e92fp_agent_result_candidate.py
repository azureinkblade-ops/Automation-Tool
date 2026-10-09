"""Fake-only terminal-text candidate checks; no receiver or result-store write."""

import json

import pytest

from tests.hermes_core.test_sqlite_delegation_delivery import make_receipt
from tests.hermes_core.test_sqlite_delegation_store import make_envelope, make_lease
from tools.hermes_core.agent_receiver_lineage import bind_receiver_lineage
from tools.hermes_core.agent_result_candidate import decode_agent_result_candidate
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.receiver_adapter import VerifiedResult


def lineage(agent):
    task = make_envelope(requested_target_agent_id=agent)
    lease = make_lease(task)
    return bind_receiver_lineage(task, lease, make_receipt(task, lease), receiver_agent_id=agent)


def candidate():
    return {
        "schema_version": "1", "outcome": "SUCCEEDED",
        "result_payload": {"summary": "Synthetic result."},
        "output_manifest": [], "evidence_manifest": [],
        "error_code": None, "error_summary": None,
    }


@pytest.mark.parametrize("agent", [
    "kilo-cli-agent", "opencode-cli-agent",
])
def test_structured_candidate_is_bound_but_not_verified(agent):
    bound = lineage(agent)
    payload = candidate()
    result = decode_agent_result_candidate(
        bound, VerifiedResult(valid=True, payload={"type": "text", "text": json.dumps(payload)}),
    )
    assert result.lineage is bound
    assert json.loads(result.candidate_json) == payload
    assert not hasattr(result, "validated_result_schema_id")


@pytest.mark.parametrize("text", [
    "EA4E20_OPENCODE_FULLY_GOVERNED_OK",
    "A successful response.",
    "{not-json}",
    "NaN",
    '{"schema_version":"1","schema_version":"2"}',
    "[]",
])
def test_unstructured_or_nonfinite_terminal_text_is_denied(text):
    with pytest.raises(DelegationIntegrityError):
        decode_agent_result_candidate(
            lineage("opencode-cli-agent"),
            VerifiedResult(valid=True, payload={"type": "text", "text": text}),
        )


@pytest.mark.parametrize("change", [
    lambda data: data.update(schema_version="2"),
    lambda data: data.pop("evidence_manifest"),
    lambda data: data.update(output_manifest=["not-an-object"]),
    lambda data: data.update(outcome="UNKNOWN"),
    lambda data: data.update(error_code="UNEXPECTED"),
])
def test_divergent_candidate_contract_is_denied(change):
    bound = lineage("kilo-cli-agent")
    payload = candidate()
    change(payload)
    with pytest.raises(DelegationIntegrityError):
        decode_agent_result_candidate(
            bound, VerifiedResult(valid=True, payload={"type": "text", "text": json.dumps(payload)}),
        )


def test_adapter_parse_success_alone_is_insufficient():
    bound = lineage("kilo-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        decode_agent_result_candidate(
            bound, VerifiedResult(valid=True, payload={"type": "text", "text": "done"}),
        )


def test_codex_result_uses_separate_contract():
    with pytest.raises(DelegationIntegrityError):
        decode_agent_result_candidate(
            lineage("codex-cli-agent"),
            VerifiedResult(valid=True, payload={"type": "text", "text": json.dumps(candidate())}),
        )
