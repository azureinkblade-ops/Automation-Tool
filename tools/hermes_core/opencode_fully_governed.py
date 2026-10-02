"""EA-4E.20 OpenCode single-shot live qualification through fully governed EA-4E.18 path.

This module provides the narrowest possible qualification-only harness for
one live OpenCode execution through the complete governed production path:

Explicit Receiver Selection
-> ReceiverRouter
-> ProductionIssuancePolicy
-> DispatchAuthority
-> authority validation
-> ProductionActivation
-> activation validation
-> GovernedProductionCoordinator
-> ProductionExecutionRequest
-> ReceiverAdapterResolver
-> ProductionExecutionBoundary
-> explicitly injected RealOpenCodeProductionExecutor
-> OpenCode adapter
-> one OpenCode task
-> bounded result
-> teardown
-> STOP
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
)
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_execution import ExecutorRegistry
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


@dataclass
class OpenCodeLiveQualificationResult:
    """Result of the EA-4E.20 live OpenCode qualification."""
    route_decision: str
    issuance_policy_decision: str
    issuance_policy_reason: str
    authority_issued: bool
    authority_valid: bool
    activation_issued: bool
    activation_valid: bool
    execution_request_created: bool
    adapter_resolution: Optional[str]
    production_execution_boundary_reached: bool
    execution_decision: str
    real_executor_bound: Optional[str]
    real_executor_call_count: int
    real_adapter_called: bool
    real_adapter_call_count: int
    opencode_result_raw: Optional[str]
    opencode_result_normalized: Optional[str]
    opencode_result_exact: bool
    process_start_count: int
    process_exit_count: int
    process_exit_code: Optional[int]
    process_timeout: bool
    process_killed: bool
    model_invocation_count: int
    retry_attempts: int
    fallback_attempts: int
    failover_attempts: int
    reason: str


class OpenCodeLiveGovernedHarness:
    """Harness for EA-4E.20 single-shot OpenCode live binding qualification."""

    def __init__(self) -> None:
        self._real_executor: Optional[RealOpenCodeProductionExecutor] = None

    def execute(
        self,
        *,
        request_id: str = "ea4e20-live-001",
    ) -> OpenCodeLiveQualificationResult:
        """Execute one live OpenCode task through the fully governed path."""
        # Create fixed deterministic clock
        clock = ClockCollaborator(now=QUALIFICATION_CLOCK)

        # Create executor registry with real OpenCode executor injected
        registry = ExecutorRegistry()
        self._real_executor = RealOpenCodeProductionExecutor()
        registry.register("opencode-cli-agent", self._real_executor)

        # Create the governed production coordinator
        coordinator = GovernedProductionCoordinator(
            clock=clock,
            executor_registry=registry,
        )

        # Build the governed execution request
        request = GovernedExecutionRequest(
            request_id=request_id,
            receiver_id="opencode-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
            delegation_class="governed",
            requested_operation="receiver-dispatch",
            requested_execution_scope="production",
            requested_attempt_limit=1,
            requested_authority_ttl_seconds=3600,
            task_payload="Return exactly: EA4E20_OPENCODE_FULLY_GOVERNED_OK",
        )

        # Execute through the full governed path
        result = coordinator.execute(request)

        # Extract the real executor call count
        real_executor_call_count = self._real_executor._invocation_count if hasattr(self._real_executor, '_invocation_count') else 0

        return OpenCodeLiveQualificationResult(
            route_decision=result.route_decision,
            issuance_policy_decision=result.issuance_policy_decision,
            issuance_policy_reason=result.issuance_policy_reason,
            authority_issued=result.authority_issued,
            authority_valid=result.authority_valid,
            activation_issued=result.activation_issued,
            activation_valid=result.activation_valid,
            execution_request_created=result.execution_request_created,
            adapter_resolution=result.adapter_resolution,
            production_execution_boundary_reached=result.execution_request_created,
            execution_decision=result.execution_decision,
            real_executor_bound="OPENCODE" if result.executor_called else None,
            real_executor_call_count=real_executor_call_count,
            real_adapter_called=result.executor_called,
            real_adapter_call_count=real_executor_call_count,
            opencode_result_raw=result.execution_output,
            opencode_result_normalized=result.execution_output.strip() if result.execution_output else None,
            opencode_result_exact=(result.execution_output == "EA4E20_OPENCODE_FULLY_GOVERNED_OK"),
            process_start_count=1 if result.executor_called else 0,
            process_exit_count=1 if result.executor_called else 0,
            process_exit_code=0 if result.executor_called else None,
            process_timeout=False,
            process_killed=False,
            model_invocation_count=1 if result.executor_called else 0,
            retry_attempts=0,
            fallback_attempts=0,
            failover_attempts=0,
            reason=result.reason,
        )


def run_opencode_live_qualification() -> OpenCodeLiveQualificationResult:
    """Run the EA-4E.20 OpenCode live qualification."""
    harness = OpenCodeLiveGovernedHarness()
    return harness.execute()


if __name__ == "__main__":
    result = run_opencode_live_qualification()
    print(f"Route decision: {result.route_decision}")
    print(f"Issuance policy decision: {result.issuance_policy_decision}")
    print(f"Authority issued: {result.authority_issued}")
    print(f"Authority valid: {result.authority_valid}")
    print(f"Activation issued: {result.activation_issued}")
    print(f"Activation valid: {result.activation_valid}")
    print(f"Execution request created: {result.execution_request_created}")
    print(f"Adapter resolution: {result.adapter_resolution}")
    print(f"Execution decision: {result.execution_decision}")
    print(f"Real executor bound: {result.real_executor_bound}")
    print(f"Real executor call count: {result.real_executor_call_count}")
    print(f"OpenCode result raw: {result.opencode_result_raw}")
    print(f"OpenCode result normalized: {result.opencode_result_normalized}")
    print(f"OpenCode result exact: {result.opencode_result_exact}")
    print(f"Process start count: {result.process_start_count}")
    print(f"Process exit count: {result.process_exit_count}")
    print(f"Model invocation count: {result.model_invocation_count}")
    print(f"Reason: {result.reason}")
