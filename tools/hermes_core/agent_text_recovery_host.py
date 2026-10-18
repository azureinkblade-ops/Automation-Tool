"""Default-disabled host for durable bounded agent text recovery."""

from tools.hermes_core.agent_codex_terminal_witness import load_codex_terminal_observation
from tools.hermes_core.agent_receiver_start_fence import SQLiteAgentReceiverStartFenceStore
from tools.hermes_core.agent_start_witness import load_bound_agent_start
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.agent_text_result import AGENT_TEXT_SCHEMA_ID
from tools.hermes_core.agent_text_return import return_bound_agent_text
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError, DelegationNotFoundError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.sqlite_delegation_result_store import SQLiteDelegationResultStore
from tools.hermes_core.sqlite_delegation_store import SQLiteDelegationStore
from tools.hermes_core.sqlite_execution_start_store import SQLiteExecutionStartStore


class AgentTextRecoveryHost:
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
            raise DelegationIntegrityError("agent text recovery gate invalid")
        if (type(authority) is not SQLiteDelegationStore
                or type(start) is not SQLiteExecutionStartStore
                or type(captures) is not SQLiteAgentTerminalCaptureStore
                or type(registry) is not CodexInvocationRegistry
                or type(results) is not SQLiteDelegationResultStore
                or captures.authority.path != authority.path
                or captures.start is not start
                or results.path != authority.path):
            raise DelegationIntegrityError("agent text recovery stores are not bound")
        if receiver_starts is not None and (
            type(receiver_starts) is not SQLiteAgentReceiverStartFenceStore
            or receiver_starts.authority.path != authority.path
            or receiver_starts.start is not start
        ):
            raise DelegationIntegrityError("agent text receiver start fence is not bound")
        self._stores = authority, start, captures, registry, results
        self._receiver_starts = receiver_starts
        self._enabled = enabled

    def _require_enabled_attempt(self, attempt_id: str):
        if not self._enabled:
            raise DelegationIntegrityError("agent text recovery is disabled")
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("agent text attempt identity missing")

    def recover(self, attempt_id: str):
        self._require_enabled_attempt(attempt_id)
        return return_bound_agent_text(*self._stores, attempt_id)

    def inspect(self, attempt_id: str) -> str:
        """Report durable progress without starting an agent or returning text."""
        self._require_enabled_attempt(attempt_id)
        authority, start, captures, registry, results = self._stores
        receipt = authority.get_receipt(attempt_id)
        task = authority.get_delegation(receipt.delegation_id)
        if (task.expected_result_schema_id != AGENT_TEXT_SCHEMA_ID
                or receipt.receiver_agent_id not in {
                    "codex-cli-agent", "kilo-cli-agent", "opencode-cli-agent",
                }):
            raise DelegationIntegrityError("agent text recovery schema or receiver denied")
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
                    or result.result_payload.get("task_input_hash") != task.task_input_hash
                    or result.result_payload.get("receiver_receipt_hash") != receipt.artifact_hash
                    or delivery.result_id != result.result_id
                    or delivery.result_hash != result.artifact_hash
                    or len(messages) != 1
                    or authority.message_body(messages[0].message_id) != {
                        "result": result.to_canonical_dict(),
                        "result_delivery": delivery.to_canonical_dict(),
                    }):
                raise DelegationIntegrityError("agent text delivery linkage mismatch")
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
        elif captures.get(attempt_id) is None:
            if (self._receiver_starts is not None
                    and self._receiver_starts.get(attempt_id) is not None):
                return "RECEIVER_START_UNKNOWN"
            return "NO_TERMINAL_EVIDENCE"
        return "TERMINAL_EVIDENCE_AVAILABLE"
