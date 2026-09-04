"""EA-4E.16 OpenCode live binding qualification through ProductionExecutionBoundary.

This module provides the narrowest possible qualification-only real OpenCode executor
for the reusable production execution boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.opencode_adapter import OpenCodeReceiverAdapter, OpenCodeLiveProcess
from tools.hermes_core.production_execution import (
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
    ProductionExecutorProtocol,
    ProductionExecutorResult,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    ExecutionAuthorityValidator,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    ProductionActivationValidator,
    compute_ea4e11_activation_contract_id,
)


class RealOpenCodeProductionExecutor:
    """Qualification-only real OpenCode executor for ProductionExecutionBoundary.

    Implements the ProductionExecutorProtocol.
    Binds only opencode-cli-agent.
    Makes one adapter call per executor call.
    No retry, no fallback, no receiver selection.
    """

    def __init__(self) -> None:
        pass

    @property
    def executor_id(self) -> str:
        return "real-opencode-production-executor"

    def execute(self, request: ProductionExecutionRequest) -> ProductionExecutorResult:
        """Execute one OpenCode task through the adapter."""
        adapter = OpenCodeReceiverAdapter(process_impl=OpenCodeLiveProcess())
        outcome = adapter.execute(
            idempotency_key=f"ea4e16-{uuid.uuid4()}",
            launch_attempt_id=f"ea4e16-launch-{uuid.uuid4()}",
            delegation_id=f"ea4e16-delegation-{uuid.uuid4()}",
            stdin_data="",
            task=request.task_payload,
        )

        if outcome.verified_result and outcome.verified_result.valid:
            text = outcome.verified_result.payload.get("text", "")
            return ProductionExecutorResult(
                executor_id=self.executor_id,
                execution_status="SUCCESS",
                output=text,
                reason="OPENCODE_EXECUTION_COMPLETE",
            )

        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="FAILED",
            output=None,
            reason="OPENCODE_EXECUTION_FAILED",
        )


class OpenCodeLiveBindingHarness:
    """Harness for EA-4E.16 single-shot OpenCode live binding qualification."""

    def __init__(self) -> None:
        from tools.hermes_core.receiver_router import get_default_router
        self._router = get_default_router()
        self._authority_validator = ExecutionAuthorityValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._activation_validator = ProductionActivationValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._invocation_count = 0
        self._max_invocations = 1

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def execute(
        self,
        *,
        receiver_id: str,
        authority: Optional[DispatchAuthority],
        activation: Optional[ProductionActivation],
        execution_request: ProductionExecutionRequest,
    ) -> "OpenCodeLiveBindingResult":
        """Execute through the full production boundary with real OpenCode."""
        from tools.hermes_core.receiver_router import RoutingRequest
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return OpenCodeLiveBindingResult(
                route_decision=route_result.route_decision,
                authority_valid=False,
                activation_valid=False,
                execution_decision="REJECT",
                reason=route_result.route_reason,
            )

        authority_result = self._authority_validator.validate(authority, route_result)
        if authority_result.dispatch_decision != "AUTHORIZED":
            return OpenCodeLiveBindingResult(
                route_decision=authority_result.route_decision,
                authority_valid=authority_result.authority_valid,
                activation_valid=False,
                execution_decision="REJECT",
                reason=authority_result.reason,
            )

        activation_result = self._activation_validator.validate(
            activation, receiver_id=receiver_id
        )
        if activation_result.dispatch_decision != "AUTHORIZED":
            return OpenCodeLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=False,
                execution_decision="REJECT",
                reason=activation_result.reason,
            )

        if self._invocation_count >= self._max_invocations:
            return OpenCodeLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                execution_decision="REJECT",
                reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
            )

        if execution_request.attempt_limit < 1:
            return OpenCodeLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                execution_decision="REJECT",
                reason="EXECUTION_BUDGET_EXHAUSTED",
            )

        self._invocation_count += 1
        executor = RealOpenCodeProductionExecutor()
        executor_result = executor.execute(execution_request)

        return OpenCodeLiveBindingResult(
            route_decision="SELECTED",
            authority_valid=True,
            activation_valid=True,
            execution_decision="EXECUTE",
            reason=executor_result.reason,
            executor_id=executor_result.executor_id,
            executor_call_count=1,
            real_adapter_called=True,
            real_adapter_call_count=1,
            executor_status=executor_result.execution_status,
            executor_output=executor_result.output,
        )


@dataclass
class OpenCodeLiveBindingResult:
    route_decision: str
    authority_valid: bool
    activation_valid: bool
    execution_decision: str
    reason: str
    executor_id: Optional[str] = None
    executor_call_count: int = 0
    real_adapter_called: bool = False
    real_adapter_call_count: int = 0
    executor_status: Optional[str] = None
    executor_output: Optional[str] = None
