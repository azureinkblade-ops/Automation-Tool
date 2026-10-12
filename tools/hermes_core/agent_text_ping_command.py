"""Pure Kilo/OpenCode command plan for one accepted, bounded agent ping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tools.hermes_core.agent_invocation_bridge import AgentInvocationBridge
from tools.hermes_core.agent_ping_result import AGENT_PING_SCHEMA_ID
from tools.hermes_core.agent_start_witness import DurableAgentStart
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.receiver_adapter import QualifiedRuntimeBinding

if TYPE_CHECKING:
    from tools.hermes_core.opencode_adapter import OpenCodeTrustedConfig


_TEXT_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})


@dataclass(frozen=True)
class AgentTextPingCommand:
    attempt_id: str
    receiver_agent_id: str
    task_input_hash: str
    bridge_hash: str
    runtime_run_id: str
    argv: tuple[str, ...]
    argv_hash: str


def build_agent_text_ping_command(
    witness: DurableAgentStart,
    bridge: AgentInvocationBridge,
    *,
    opencode_config: OpenCodeTrustedConfig | None = None,
    opencode_binding: QualifiedRuntimeBinding | None = None,
) -> AgentTextPingCommand:
    """Shape a fixed ping; this neither verifies runtime authority nor starts it."""
    receiver, message = build_agent_text_ping_message(witness, bridge)
    invocation = witness.bound.invocation
    if receiver == "kilo-cli-agent":
        from tools.hermes_core.kilo_adapter import build_kilo_argv

        if opencode_config is not None or opencode_binding is not None:
            raise DelegationIntegrityError("Kilo ping received OpenCode binding")
        argv = tuple(build_kilo_argv({"task_message": message}, {}, invocation.runtime_run_id))
    else:
        from tools.hermes_core.opencode_adapter import (
            OpenCodeTrustedConfig, build_opencode_argv,
        )

        if (type(opencode_config) is not OpenCodeTrustedConfig
                or type(opencode_binding) is not QualifiedRuntimeBinding):
            raise DelegationIntegrityError("OpenCode ping binding missing")
        argv = tuple(build_opencode_argv(
            opencode_config, opencode_binding,
            runtime_run_id=invocation.runtime_run_id,
            task_message=message,
        ).to_list())
    return AgentTextPingCommand(
        attempt_id=witness.lease.attempt_id,
        receiver_agent_id=receiver,
        task_input_hash=witness.task.task_input_hash,
        bridge_hash=bridge.artifact_hash,
        runtime_run_id=invocation.runtime_run_id,
        argv=argv,
        argv_hash=sha256_payload(list(argv)),
    )


def build_agent_text_ping_message(
    witness: DurableAgentStart, bridge: AgentInvocationBridge,
) -> tuple[str, str]:
    """Validate an accepted ping and return its receiver-specific fixed prompt."""
    if type(witness) is not DurableAgentStart or type(bridge) is not AgentInvocationBridge:
        raise DelegationIntegrityError("text ping inputs denied")
    task = witness.task
    invocation = witness.bound.invocation
    receiver = witness.receipt.receiver_agent_id
    if (receiver not in _TEXT_RECEIVERS
            or task.requested_target_agent_id != receiver
            or task.operation != "agent_ping"
            or task.objective != "Acknowledge this ping."
            or task.instructions != ""
            or task.input_manifest
            or task.scope.read_paths or task.scope.write_paths
            or task.scope.allowed_tools
            or task.expected_result_schema_id != AGENT_PING_SCHEMA_ID
            or not task.artifact_hash or not task.task_input_hash
            or bridge.attempt_id != witness.lease.attempt_id
            or bridge.receiver_agent_id != receiver
            or bridge.receipt_hash != witness.receipt.artifact_hash
            or bridge.launch_attempt_hash != witness.launch.artifact_hash
            or bridge.start_result_hash != witness.start_result.artifact_hash
            or not bridge.verify_hash()):
        raise DelegationIntegrityError("text ping task or bridge mismatch")
    message = " ".join((
        "Return only one JSON object with exactly these top-level keys:",
        "schema_version, outcome, result_payload, output_manifest,",
        "evidence_manifest, error_code, error_summary.",
        "Set schema_version to the string 1 and outcome to the string SUCCEEDED.",
        "Set result_payload to an object with exactly task_input_hash equal to",
        f"{task.task_input_hash}, receiver_receipt_hash equal to",
        f"{witness.receipt.artifact_hash}, and statement equal to {receiver}:PING_OK.",
        "Set output_manifest to an empty array. Set evidence_manifest to one",
        "object with ordinal as numeric 0, evidence_type as the string",
        "receiver_acceptance_sha256, and sha256 equal to",
        f"{witness.receipt.artifact_hash}.",
        "Set error_code and error_summary to JSON null. Encode every other",
        "value as a JSON string. Do not add markdown or prose.",
    ))
    return receiver, message
