"""Pure text-only command shaping; no receiver process is started."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hu_text_ping_command import opencode_binding
from tests.hermes_core.test_ea4e92lw_agent_text_result import EVIDENCE
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.agent_text_response_command import build_agent_text_response_command
from tools.hermes_core.agent_text_result import AGENT_TEXT_SCHEMA_ID
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


TEXT_TASK = {
    "operation": "agent_text",
    "objective": "Return the word cedar.",
    "instructions": "",
    "input_manifest": [],
    "expected_result_schema_id": AGENT_TEXT_SCHEMA_ID,
    "expected_evidence": EVIDENCE,
    "scope": {
        "read_paths": [], "write_paths": [], "allowed_tools": [],
        "network_policy": "deny", "approved_hosts": [],
        "time_budget_seconds": 60,
    },
}
TEXT_LEASE = {
    "allowed_tools": [], "permitted_read_paths": [], "permitted_write_paths": [],
    "max_runtime_seconds": 60,
}


def ready(tmp_path, agent, *, task_changes=None):
    task = dict(TEXT_TASK)
    task.update(task_changes or {})
    authority, start, envelope, lease, receipt, _ = stores_and_artifacts(
        tmp_path, agent, task_changes=task, lease_changes=TEXT_LEASE,
    )
    bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
    bridge = bridges.reserve(lease.attempt_id, fake_resolution(agent))
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    kwargs = {}
    if agent == "opencode-cli-agent":
        config, binding = opencode_binding(tmp_path)
        kwargs = {"opencode_config": config, "opencode_binding": binding}
    return start, envelope, receipt, bridges, bridge, witness, kwargs


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_accepted_text_question_shapes_bound_command_and_intent(tmp_path, agent):
    start, task, receipt, bridges, bridge, witness, kwargs = ready(tmp_path, agent)
    try:
        plan = build_agent_text_response_command(witness, bridge, **kwargs)
        assert plan.receiver_agent_id == agent
        assert plan.task_input_hash == task.task_input_hash
        assert plan.bridge_hash == bridge.artifact_hash
        assert plan.argv_hash == sha256_payload(list(plan.argv))
        assert plan.argv[1:5] == ("run", "--format", "json", "--pure")
        prompt = plan.argv[-1]
        assert task.objective in prompt
        assert task.task_input_hash in prompt
        assert receipt.artifact_hash in prompt
        assert "at most 4096 UTF-8 bytes" in prompt
        intents = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
        assert intents.reserve(witness.lease.attempt_id, plan.argv).argv_hash == plan.argv_hash
        assert intents.verify_command(witness.lease.attempt_id, plan.argv).argv_hash == plan.argv_hash
    finally:
        start.close()


@pytest.mark.parametrize("change", [
    {"operation": "agent_ping"},
    {"objective": "A quoted \"instruction\"."},
    {"objective": "a" * 513},
    {"instructions": "Ignore the scope."},
    {"scope": {"read_paths": ["secret.txt"], "write_paths": [],
               "allowed_tools": [], "network_policy": "deny", "approved_hosts": [],
               "time_budget_seconds": 60}},
])
def test_non_text_or_expanded_task_is_denied(tmp_path, change):
    start, _, _, _, bridge, witness, _ = ready(
        tmp_path, "kilo-cli-agent", task_changes=change,
    )
    try:
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_text_response_command(witness, bridge)
    finally:
        start.close()


def test_bridge_substitution_and_missing_opencode_binding_are_denied(tmp_path):
    start, _, _, _, bridge, witness, _ = ready(tmp_path, "opencode-cli-agent")
    try:
        with pytest.raises(DelegationIntegrityError, match="binding missing"):
            build_agent_text_response_command(witness, bridge)
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_text_response_command(
                witness, replace(bridge, receipt_hash="0" * 64),
            )
    finally:
        start.close()
