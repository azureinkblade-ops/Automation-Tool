"""Synthetic Kilo/OpenCode terminal transport-to-candidate checks."""

import json
from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fp_agent_result_candidate import candidate
from tests.hermes_core.test_ea4e92fq_agent_invocation_binding import artifacts
from tools.hermes_core.agent_receiver_lineage import bind_agent_invocation
from tools.hermes_core.agent_result_candidate import bind_terminal_agent_candidate
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.receiver_adapter import ExecutionOutcome, InvocationRecord, VerifiedResult


def bound_outcome(agent):
    task, lease, receipt, launch = artifacts(agent)
    bound = bind_agent_invocation(task, lease, receipt, launch, receiver_agent_id=agent)
    record = InvocationRecord(
        idempotency_key=bound.idempotency_key, runtime_run_id=bound.runtime_run_id,
        start_state="started", pid=1234, argv_hash="a" * 64,
        terminal_state="completed" if agent == "kilo-cli-agent" else "TERMINAL",
    )
    outcome = ExecutionOutcome(
        process_started=True, replayed=False, record=record,
        verified_result=VerifiedResult(
            valid=True, payload={"type": "text", "text": json.dumps(candidate())},
        ),
    )
    return bound, outcome


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_matching_fake_terminal_outcome_yields_candidate_only(agent):
    bound, outcome = bound_outcome(agent)
    result = bind_terminal_agent_candidate(bound, outcome)
    assert result.lineage == bound.lineage
    assert json.loads(result.candidate_json)["schema_version"] == "1"
    assert not hasattr(result, "artifact_hash")


@pytest.mark.parametrize("change", [
    lambda outcome: replace(outcome, process_started=False),
    lambda outcome: replace(outcome, replayed=True),
    lambda outcome: replace(outcome, record=replace(outcome.record, idempotency_key="other")),
    lambda outcome: replace(outcome, record=replace(outcome.record, runtime_run_id="other")),
    lambda outcome: replace(outcome, record=replace(outcome.record, terminal_state="error")),
    lambda outcome: replace(outcome, record=replace(outcome.record, pid=None)),
    lambda outcome: replace(outcome, record=None),
    lambda outcome: replace(outcome, verified_result=VerifiedResult(valid=False, payload={})),
])
def test_nonterminal_or_divergent_fake_outcome_is_denied(change):
    bound, outcome = bound_outcome("kilo-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        bind_terminal_agent_candidate(bound, change(outcome))


def test_codex_adapter_uses_separate_result_contract():
    bound, outcome = bound_outcome("opencode-cli-agent")
    with pytest.raises(DelegationIntegrityError):
        bind_terminal_agent_candidate(
            replace(bound, lineage=replace(bound.lineage, receiver_agent_id="codex-cli-agent")),
            outcome,
        )
