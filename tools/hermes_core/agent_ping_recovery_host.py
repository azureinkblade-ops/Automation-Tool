"""Explicit, default-disabled host for durable delegated ping recovery."""

from tools.hermes_core.agent_ping_return import return_bound_agent_ping
from tools.hermes_core.agent_codex_terminal_witness import load_codex_terminal_observation
from tools.hermes_core.agent_ping_result import AGENT_PING_SCHEMA_ID
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


class AgentPingRecoveryHost:
    def __init__(
        self,
        authority: SQLiteDelegationStore,
        start: SQLiteExecutionStartStore,
        captures: SQLiteAgentTerminalCaptureStore,
        registry: CodexInvocationRegistry,
        results: SQLiteDelegationResultStore,
        *,
        enabled: bool = False,
        receiver_starts: SQLiteAgentReceiverStartFenceStore | None = None,
    ):
        if type(enabled) is not bool:
            raise DelegationIntegrityError("agent ping recovery gate invalid")
        if (type(authority) is not SQLiteDelegationStore
                or type(start) is not SQLiteExecutionStartStore
                or type(captures) is not SQLiteAgentTerminalCaptureStore
                or type(registry) is not CodexInvocationRegistry
                or type(results) is not SQLiteDelegationResultStore
                or captures.authority.path != authority.path
                or captures.start is not start
                or results.path != authority.path):
            raise DelegationIntegrityError("agent ping recovery stores are not bound")
        if receiver_starts is not None and (
            type(receiver_starts) is not SQLiteAgentReceiverStartFenceStore
            or receiver_starts.authority.path != authority.path
            or receiver_starts.start is not start
        ):
            raise DelegationIntegrityError("receiver start fence is not bound")
        self._stores = authority, start, captures, registry, results
        self._receiver_starts = receiver_starts
        self._enabled = enabled

    def recover(self, attempt_id: str):
        self._require_enabled_attempt(attempt_id)
        return return_bound_agent_ping(*self._stores, attempt_id)

    def _require_enabled_attempt(self, attempt_id: str):
        if not self._enabled:
            raise DelegationIntegrityError("agent ping recovery is disabled")
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("agent ping attempt identity missing")

    def inspect(self, attempt_id: str) -> str:
        """Read durable progress without starting or returning an agent result."""
        self._require_enabled_attempt(attempt_id)
        authority, start, captures, registry, results = self._stores
        receipt = authority.get_receipt(attempt_id)
        task = authority.get_delegation(receipt.delegation_id)
        if task.expected_result_schema_id != AGENT_PING_SCHEMA_ID:
            raise DelegationIntegrityError("agent ping schema is not supported")
        try:
            result = results.get_result(attempt_id)
        except DelegationNotFoundError:
            result = None
        if result is not None:
            delivery_id = "delivery-" + sha256_payload({
                "result_id": result.result_id,
                "recipient_agent_id": task.originator_agent_id,
                "delivery_revision": 0,
            })
            delivery = results.get_delivery(delivery_id)
            messages = [message for message in authority.list_mailbox(task.originator_agent_id)
                        if message.attempt_id == attempt_id
                        and message.message_type == "RESULT_DELIVERY"
                        and message.idempotency_key == delivery_id]
            if (result.delegation_id != task.delegation_id
                    or delivery.result_id != result.result_id
                    or delivery.result_hash != result.artifact_hash
                    or len(messages) != 1
                    or authority.message_body(messages[0].message_id) != {
                        "result": result.to_canonical_dict(),
                        "result_delivery": delivery.to_canonical_dict(),
                    }):
                raise DelegationIntegrityError("agent ping delivery linkage mismatch")
            return "MESSAGE_AVAILABLE"
        if (receipt.receiver_agent_id in {"kilo-cli-agent", "opencode-cli-agent"}
                and self._receiver_starts is not None
                and (authority.delegation_status(task.delegation_id) != "CREATED"
                     or authority.lease_status(receipt.capability_lease_id) != "ACTIVE")
                and self._receiver_starts.get(attempt_id) is not None):
            return "RECEIVER_START_UNKNOWN"
        witness = load_bound_agent_start(authority, start, attempt_id)
        if receipt.receiver_agent_id == "codex-cli-agent":
            if registry.get(witness.bound.invocation.idempotency_key) is None:
                return "NO_TERMINAL_EVIDENCE"
            load_codex_terminal_observation(witness, registry)
        elif receipt.receiver_agent_id in {"kilo-cli-agent", "opencode-cli-agent"}:
            if captures.get(attempt_id) is None:
                if (self._receiver_starts is not None
                        and self._receiver_starts.get(attempt_id) is not None):
                    return "RECEIVER_START_UNKNOWN"
                return "NO_TERMINAL_EVIDENCE"
        else:
            raise DelegationIntegrityError("agent ping receiver is not supported")
        return "TERMINAL_EVIDENCE_AVAILABLE"
