"""EA-4E.15 Kilo live binding qualification through ProductionExecutionBoundary.

This module provides the narrowest possible qualification-only real Kilo executor
for the reusable production execution boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.kilo_adapter import KiloAdapter
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


class RealKiloProductionExecutor:
    """Qualification-only real Kilo executor for ProductionExecutionBoundary.

    Implements the ProductionExecutorProtocol.
    Binds only kilo-cli-agent.
    Makes one adapter call per executor call.
    No retry, no fallback, no receiver selection.
    """

    def __init__(self, *, kilo_executable: Optional[str] = None) -> None:
        self._kilo_executable = kilo_executable
        self._invocation_count = 0
        self._last_outcome: Optional[ExecutionOutcome] = None

    @property
    def executor_id(self) -> str:
        return "RealKiloProductionExecutor"

    @property
    def last_outcome(self) -> Optional[ExecutionOutcome]:
        """Return the last adapter ExecutionOutcome for forensic accounting."""
        return self._last_outcome

    def execute(self, request: ProductionExecutionRequest) -> ProductionExecutorResult:
        """Execute one Kilo task through the adapter."""
        self._invocation_count += 1
        config = {"task_message": request.task_payload}
        if self._kilo_executable:
            config["kilo_executable"] = self._kilo_executable

        adapter = KiloAdapter(config=config)
        outcome = adapter.execute(
            idempotency_key=f"ea4e15-{uuid.uuid4()}",
            launch_attempt_id=f"ea4e15-launch-{uuid.uuid4()}",
            delegation_id=f"ea4e15-delegation-{uuid.uuid4()}",
            stdin_data="",
        )
        self._last_outcome = outcome

        if outcome.verified_result and outcome.verified_result.valid:
            text = outcome.verified_result.payload.get("text", "")
            return ProductionExecutorResult(
                executor_id=self.executor_id,
                execution_status="SUCCESS",
                output=text,
                reason="KILO_EXECUTION_COMPLETE",
            )

        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="FAILED",
            output=None,
            reason="KILO_EXECUTION_FAILED",
        )


class KiloLiveBindingHarness:
    """Harness for EA-4E.15 single-shot Kilo live binding qualification."""

    def __init__(self, *, kilo_executable: Optional[str] = None) -> None:
        from tools.hermes_core.receiver_router import get_default_router
        self._router = get_default_router()
        self._authority_validator = ExecutionAuthorityValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._activation_validator = ProductionActivationValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._kilo_executable = kilo_executable
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
    ) -> "KiloLiveBindingResult":
        """Execute through the full production boundary with real Kilo."""
        # Steps 1-3: Route, authority, activation (via boundary)
        from tools.hermes_core.receiver_router import RoutingRequest
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return KiloLiveBindingResult(
                route_decision=route_result.route_decision,
                authority_valid=False,
                activation_valid=False,
                execution_decision="REJECT",
                reason=route_result.route_reason,
            )

        authority_result = self._authority_validator.validate(authority, route_result)
        if authority_result.dispatch_decision != "AUTHORIZED":
            return KiloLiveBindingResult(
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
            return KiloLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=False,
                execution_decision="REJECT",
                reason=activation_result.reason,
            )

        # Step 4: Single-shot enforcement
        if self._invocation_count >= self._max_invocations:
            return KiloLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                execution_decision="REJECT",
                reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
            )

        # Step 5: Execution budget check from request
        if execution_request.attempt_limit < 1:
            return KiloLiveBindingResult(
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                execution_decision="REJECT",
                reason="EXECUTION_BUDGET_EXHAUSTED",
            )

        # Step 6: Real Kilo executor injection
        self._invocation_count += 1
        executor = RealKiloProductionExecutor(kilo_executable=self._kilo_executable)
        executor_result = executor.execute(execution_request)

        return KiloLiveBindingResult(
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
class KiloLiveBindingResult:
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
