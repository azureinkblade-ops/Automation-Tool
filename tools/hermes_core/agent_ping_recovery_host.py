"""Explicit, default-disabled host for durable delegated ping recovery."""

from tools.hermes_core.agent_ping_return import return_bound_agent_ping
from tools.hermes_core.agent_terminal_capture import SQLiteAgentTerminalCaptureStore
from tools.hermes_core.codex_adapter import CodexInvocationRegistry
from tools.hermes_core.delegated_task import DelegationIntegrityError
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
    ):
        if type(enabled) is not bool:
            raise DelegationIntegrityError("agent ping recovery gate invalid")
        self._stores = authority, start, captures, registry, results
        self._enabled = enabled

    def recover(self, attempt_id: str):
        if not self._enabled:
            raise DelegationIntegrityError("agent ping recovery is disabled")
        if type(attempt_id) is not str or not attempt_id:
            raise DelegationIntegrityError("agent ping attempt identity missing")
        return return_bound_agent_ping(*self._stores, attempt_id)
