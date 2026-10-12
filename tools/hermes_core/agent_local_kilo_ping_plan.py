"""Non-launchable Linux Kilo candidate for an accepted delegated ping."""

from copy import deepcopy

from tools.hermes_core.agent_invocation_bridge import AgentInvocationBridge
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.agent_text_ping_command import build_agent_text_ping_message
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.local_kilo_inert_plan import build_inert_plan


def build_agent_local_kilo_ping_plan(
    witness: DurableAgentStart, bridge: AgentInvocationBridge,
) -> dict:
    """Bind the fixed ping to the inert Linux image; grant no launch authority."""
    receiver, message = build_agent_text_ping_message(witness, bridge)
    if receiver != "kilo-cli-agent":
        raise DelegationIntegrityError("Linux Kilo plan received another receiver")
    plan = deepcopy(build_inert_plan())
    if (plan["launch_authorized"] is not False
            or plan["provider"]["api_key"] != "EA4E_INERT_ONLY"
            or plan["agent_profile"]["live_authorized"] is not False
            or plan["agent_profile"]["permission"] != {"*": "deny"}):
        raise DelegationIntegrityError("Linux Kilo inert base changed")
    plan["schema_id"] = "hermes.agent-local-kilo-ping-plan/v1"
    plan["argv"][-1] = message
    plan["attempt_id"] = witness.lease.attempt_id
    plan["task_input_hash"] = witness.task.task_input_hash
    plan["receipt_hash"] = witness.receipt.artifact_hash
    plan["bridge_hash"] = bridge.artifact_hash
    plan["runtime_run_id"] = witness.bound.invocation.runtime_run_id
    plan["argv_hash"] = sha256_payload(plan["argv"])
    plan["launch_authorized"] = False
    plan["receiver_executed"] = False
    plan["model_invoked"] = False
    return plan
