"""Question to originator through fake text-agent terminal records only."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92gh_terminal_capture import capture_store
from tests.hermes_core.test_ea4e92lw_agent_text_result import DELIVERY_TIME
from tests.hermes_core.test_ea4e92lx_agent_text_return import body_for
from tests.hermes_core.test_ea4e92ly_agent_text_response_command import ready
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.agent_text_response_command import build_agent_text_response_command
from tools.hermes_core.agent_text_return import return_bound_agent_text
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import canonical_json
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
@pytest.mark.parametrize("forged", [False, True])
def test_text_question_to_originator_after_restart(tmp_path, agent, forged):
    start, task, receipt, bridges, bridge, witness, kwargs = ready(tmp_path, agent)
    authority = bridges.authority
    plan = build_agent_text_response_command(witness, bridge, **kwargs)
    intents = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
    assert intents.reserve(witness.lease.attempt_id, plan.argv).argv_hash == plan.argv_hash
    body = body_for(witness, text="cedar")
    if forged:
        body["result_payload"]["receiver_receipt_hash"] = "0" * 64
    outcome = terminal_outcome(witness)
    outcome = replace(
        outcome, verified_result=replace(
            outcome.verified_result,
            payload={"type": "text", "text": canonical_json(body)},
        ),
    )
    capture_store(authority, start).capture(witness.lease.attempt_id, outcome)
    start.close()
    start = SQLiteExecutionStartStore(tmp_path / "start.sqlite3")
    try:
        authority = SQLiteDelegationStore(authority.path)
        captures = capture_store(authority, start)
        results = SQLiteDelegationResultStore(authority.path, clock=lambda: DELIVERY_TIME)
        registry = CodexInvocationRegistry(str(tmp_path / "codex.sqlite3"))
        registry.initialize()
        if forged:
            with pytest.raises(DelegationIntegrityError):
                return_bound_agent_text(
                    authority, start, captures, registry, results,
                    witness.lease.attempt_id,
                )
            with pytest.raises(DelegationNotFoundError):
                results.get_result(witness.lease.attempt_id)
            assert authority.list_mailbox(task.originator_agent_id) == []
            return
        first = return_bound_agent_text(
            authority, start, captures, registry, results,
            witness.lease.attempt_id,
        )
        assert first[0].result_payload["text"] == "cedar"
        assert return_bound_agent_text(
            authority, start, captures, registry, results,
            witness.lease.attempt_id,
        ) == first
        mailbox = authority.list_mailbox(task.originator_agent_id)
        assert [message.message_id for message in mailbox] == [first[2]]
        authority.claim_message(
            first[2], recipient_agent_id=task.originator_agent_id,
            claim_token="originator-claim", claimed_at="2026-08-27T12:05:09Z",
            claim_expires_at="2026-08-27T12:06:00Z",
        )
        authority.acknowledge_message(
            first[2], recipient_agent_id=task.originator_agent_id,
            claim_token="originator-claim", acknowledged_at="2026-08-27T12:05:10Z",
        )
        assert authority.delivery_state(first[2]) == "ACKNOWLEDGED"
    finally:
        start.close()
