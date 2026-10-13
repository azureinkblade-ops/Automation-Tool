"""The accepted ping can be represented in Linux without launching it."""

from dataclasses import replace
from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92fz_durable_agent_start import stores_and_artifacts
from tests.hermes_core.test_ea4e92he_agent_invocation_bridge import NOW, fake_resolution
from tests.hermes_core.test_ea4e92hu_text_ping_command import PING_LEASE, PING_TASK
from tools.hermes_core.agent_invocation_bridge_store import SQLiteAgentInvocationBridgeStore
from tools.hermes_core.agent_local_kilo_ping_plan import (
    build_agent_local_kilo_ping_plan, verify_agent_local_kilo_ping_plan,
)
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_text_ping_command import build_agent_text_ping_command
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_inert_plan import build_inert_plan


def _accepted(tmp_path, agent="kilo-cli-agent"):
    authority, start, task, lease, receipt, _ = stores_and_artifacts(
        tmp_path, agent, ping=True, task_changes=PING_TASK, lease_changes=PING_LEASE,
    )
    bridges = SQLiteAgentInvocationBridgeStore(authority, start, clock=lambda: NOW)
    bridge = bridges.reserve(lease.attempt_id, fake_resolution(agent))
    witness = load_bound_agent_start(authority, start, lease.attempt_id)
    return start, witness, bridge


def test_linux_plan_binds_same_accepted_ping_without_launch(tmp_path):
    start, witness, bridge = _accepted(tmp_path)
    try:
        plan = build_agent_local_kilo_ping_plan(witness, bridge)
        windows = build_agent_text_ping_command(witness, bridge)
        inert = build_inert_plan()
        assert plan["argv"][-1] == windows.argv[-1]
        assert plan["argv"][:-1] == inert["argv"][:-1]
        assert plan["argv_hash"] == sha256_payload(plan["argv"])
        assert verify_agent_local_kilo_ping_plan(witness, bridge, plan) == plan["plan_hash"]
        assert plan["attempt_id"] == witness.lease.attempt_id
        assert plan["task_input_hash"] == witness.task.task_input_hash
        assert plan["receipt_hash"] == witness.receipt.artifact_hash
        assert plan["bridge_hash"] == bridge.artifact_hash
        assert plan["runtime_run_id"] == witness.bound.invocation.runtime_run_id
        assert plan["image_manifest"] == inert["image_manifest"]
        assert plan["entrypoint"] == ["/opt/kilo/kilo"]
        assert plan["provider"] == inert["provider"]
        assert plan["agent_profile"] == inert["agent_profile"]
        assert plan["config_delivery"] == "UNRESOLVED_NO_FILES_WRITTEN"
        assert plan["network_binding"] == "UNRESOLVED_FAKE_ONLY"
        assert plan["launch_authorized"] is False
        assert plan["receiver_executed"] is False
        assert plan["model_invoked"] is False
        assert inert["argv"][-1] != plan["argv"][-1]
    finally:
        start.close()


@pytest.mark.parametrize("field,value", [
    ("image_manifest", "sha256:" + "0" * 64),
    ("network_binding", "unexpected-network"),
    ("launch_authorized", True),
    ("bridge_hash", "0" * 64),
])
def test_plan_mutation_is_denied(tmp_path, field, value):
    start, witness, bridge = _accepted(tmp_path)
    try:
        plan = build_agent_local_kilo_ping_plan(witness, bridge)
        changed = deepcopy(plan)
        changed[field] = value
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            verify_agent_local_kilo_ping_plan(witness, bridge, changed)
        changed = deepcopy(plan)
        changed["agent_profile"]["permission"]["*"] = "allow"
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            verify_agent_local_kilo_ping_plan(witness, bridge, changed)
        changed = deepcopy(plan)
        changed["argv"][-1] = "different task"
        changed["plan_hash"] = sha256_payload({
            key: item for key, item in changed.items() if key != "plan_hash"
        })
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            verify_agent_local_kilo_ping_plan(witness, bridge, changed)
        changed = deepcopy(plan)
        changed["rootfs_readonly"] = 1
        changed["plan_hash"] = sha256_payload({
            key: item for key, item in changed.items() if key != "plan_hash"
        })
        with pytest.raises(DelegationIntegrityError, match="plan mismatch"):
            verify_agent_local_kilo_ping_plan(witness, bridge, changed)
    finally:
        start.close()


def test_other_receiver_and_changed_lineage_deny(tmp_path):
    start, witness, bridge = _accepted(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_local_kilo_ping_plan(witness, replace(bridge, receipt_hash="0" * 64))
        with pytest.raises(DelegationIntegrityError, match="task or bridge mismatch"):
            build_agent_local_kilo_ping_plan(
                replace(witness, task=replace(witness.task, operation="other")), bridge,
            )
    finally:
        start.close()

    start, witness, bridge = _accepted(tmp_path / "other", "opencode-cli-agent")
    try:
        with pytest.raises(DelegationIntegrityError, match="another receiver"):
            build_agent_local_kilo_ping_plan(witness, bridge)
    finally:
        start.close()
