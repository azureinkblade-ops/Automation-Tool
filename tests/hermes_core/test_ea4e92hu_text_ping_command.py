"""Pure command shaping only; no receiver executable is run."""

from dataclasses import replace

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92gc_terminal_text_ping import terminal_outcome
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_result_candidate import bind_terminal_agent_candidate
from tools.hermes_core.agent_ping_result import validate_agent_ping_candidate
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_ping_command import build_agent_text_ping_command
from tools.hermes_core.agent_text_process_intent import SQLiteAgentTextProcessIntentStore
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.opencode_adapter import OpenCodeTrustedConfig
from tools.hermes_core.receiver_adapter import QualifiedRuntimeBinding


PING_TASK = {
    "operation": "agent_ping",
    "objective": "Acknowledge this ping.",
    "instructions": "",
    "input_manifest": [],
    "scope": {
        "read_paths": [], "write_paths": [], "allowed_tools": [],
        "network_policy": "deny", "approved_hosts": [],
        "time_budget_seconds": 60,
    },
}
PING_LEASE = {
    "allowed_tools": [], "permitted_read_paths": [], "permitted_write_paths": [],
    "max_runtime_seconds": 60,
}


def opencode_binding(tmp_path):
    executable = tmp_path / "inert-opencode.exe"
    executable.write_bytes(b"not executable; command-shaping fixture")
    config = OpenCodeTrustedConfig(
        executable_path=str(executable), expected_sha256="a" * 64,
        expected_version="test", fixture_root=str(tmp_path),
        working_directory=str(tmp_path), output_schema_file=str(tmp_path / "schema.json"),
        spool_directory=str(tmp_path / "spool"), registry_path=str(tmp_path / "registry.db"),
        environment=(), expected_transport_contract_id="test-transport",
    )
    binding = QualifiedRuntimeBinding(
        executable=str(executable.resolve()), binary_sha256="a" * 64,
        binary_version="test", transport_contract_id="test-transport",
    )
    return config, binding


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_ping_command_uses_accepted_task_and_receiver_builder(tmp_path, agent):
    authority, start, task, lease, receipt, _ = stores_and_artifacts(
        tmp_path, agent, ping=True, task_changes=PING_TASK, lease_changes=PING_LEASE,
    )
    try:
        bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge = bridges.reserve(lease.attempt_id, fake_resolution(agent))
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        kwargs = {}
        if agent == "opencode-cli-agent":
            config, binding = opencode_binding(tmp_path)
            kwargs = {"opencode_config": config, "opencode_binding": binding}
        plan = build_agent_text_ping_command(witness, bridge, **kwargs)
        assert plan.task_input_hash == task.task_input_hash
        assert plan.bridge_hash == bridge.artifact_hash
        assert plan.runtime_run_id == witness.bound.invocation.runtime_run_id
        assert plan.argv_hash == sha256_payload(list(plan.argv))
        prompt = plan.argv[-1]
        assert task.task_input_hash in prompt
        assert receipt.artifact_hash in prompt
        assert f"{agent}:PING_OK" in prompt
        assert "schema_version, outcome, result_payload" in prompt
        assert "evidence_manifest, error_code, error_summary" in prompt
        assert '"' not in prompt and "\n" not in prompt
        candidate = bind_terminal_agent_candidate(
            witness.bound.invocation, terminal_outcome(witness),
        )
        validate_agent_ping_candidate(task, lease, receipt, candidate)
        assert plan.argv[1:5] == ("run", "--format", "json", "--pure")
        intents = SQLiteAgentTextProcessIntentStore(bridges, clock=lambda: NOW)
        assert intents.reserve(lease.attempt_id, plan.argv).argv_hash == plan.argv_hash
        assert intents.verify_command(lease.attempt_id, plan.argv).argv_hash == plan.argv_hash
    finally:
        start.close()


@pytest.mark.parametrize("agent", ["kilo-cli-agent", "opencode-cli-agent"])
def test_non_ping_and_changed_bridge_are_denied(tmp_path, agent):
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True, task_changes=PING_TASK, lease_changes=PING_LEASE,
    )
    try:
        bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge = bridges.reserve(lease.attempt_id, fake_resolution(agent))
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        kwargs = {}
        if agent == "opencode-cli-agent":
            config, binding = opencode_binding(tmp_path)
            kwargs = {"opencode_config": config, "opencode_binding": binding}
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_text_ping_command(witness, replace(bridge, receipt_hash="0" * 64), **kwargs)
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_text_ping_command(
                replace(witness, task=replace(witness.task, operation="write_report")),
                bridge, **kwargs,
            )
    finally:
        start.close()


def test_opencode_ping_requires_explicit_config_and_binding(tmp_path):
    agent = "opencode-cli-agent"
    authority, start, _, lease, _, _ = stores_and_artifacts(
        tmp_path, agent, ping=True, task_changes=PING_TASK, lease_changes=PING_LEASE,
    )
    try:
        bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
        bridge = bridges.reserve(lease.attempt_id, fake_resolution(agent))
        witness = load_bound_agent_start(authority, start, lease.attempt_id)
        with pytest.raises(DelegationIntegrityError, match="binding missing"):
            build_agent_text_ping_command(witness, bridge)
    finally:
        start.close()
