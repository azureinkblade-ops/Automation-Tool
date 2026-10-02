"""EA-4E.18 issuance-to-execution integration.

This module establishes the permanent orchestration seam connecting:
1. explicit receiver selection / routing;
2. governed authority + activation issuance; and
3. reusable production execution boundary.

This is a non-live qualification: no real receiver process is started.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingRequest,
    RoutingResult,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    ExecutionAuthorityValidator,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    compute_ea4e11_activation_contract_id,
)
from tools.hermes_core.production_execution import (
    ExecutorRegistry,
    FakeKiloExecutor,
    FakeOpenCodeExecutor,
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
    ProductionExecutionResult,
    compute_ea4e14_execution_contract_id,
)
from tools.hermes_core.production_issuance import (
    ClockCollaborator,
    ProductionIssuancePolicy,
    ProductionIssuanceRequest,
    ProductionIssuanceResult,
    compute_ea4e17_issuance_contract_id,
)


# --------------------------------------------------------------------------- #
# Integration schema
# --------------------------------------------------------------------------- #

INTEGRATION_SCHEMA_ID = "hermes.production-governed-execution.receiver-dispatch/v1"
INTEGRATION_SCHEMA_VERSION = "ea4e.18"


# --------------------------------------------------------------------------- #
# Integrated request
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GovernedExecutionRequest:
    """Request for the full governed production path.

    The receiver must already be explicitly selected.
    This request does NOT select a receiver.
    """
    request_id: str
    receiver_id: str
    router_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    delegation_class: str = "governed"
    requested_operation: str = "receiver-dispatch"
    requested_execution_scope: str = "production"
    requested_attempt_limit: int = 1
    requested_authority_ttl_seconds: int = 3600
    task_payload: str | None = None


# --------------------------------------------------------------------------- #
# Integrated result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GovernedProductionResult:
    """Structured result of the full governed production path.

    Does NOT contain secrets, tokens, or credentials.
    """
    request_id: str
    receiver_id: str
    route_decision: str
    issuance_policy_decision: str
    issuance_policy_reason: str
    authority_issued: bool
    authority_valid: Optional[bool]
    activation_issued: bool
    activation_valid: Optional[bool]
    execution_request_created: bool
    adapter_resolution: Optional[str]
    execution_decision: Optional[str]
    executor_called: bool
    execution_status: Optional[str]
    execution_output: Optional[str]
    reason: str
    attempt_count: int


# --------------------------------------------------------------------------- #
# Coordinator
# --------------------------------------------------------------------------- #

class GovernedProductionCoordinator:
    """Orchestration seam connecting routing, issuance, and execution.

    Does NOT select receivers.
    Does NOT execute real receivers by default.
    Does NOT create fallback/failover.
    """

    def __init__(
        self,
        *,
        clock: ClockCollaborator,
        executor_registry: Optional[ExecutorRegistry] = None,
        policy: Optional[ProductionIssuancePolicy] = None,
        max_invocations: int = 1,
    ) -> None:
        self._clock = clock
        self._executor_registry = executor_registry or ExecutorRegistry()
        self._policy = policy or ProductionIssuancePolicy(clock=clock)
        self._boundary = ProductionExecutionBoundary(
            executor_registry=self._executor_registry,
            authority_validator=ExecutionAuthorityValidator(
                router_contract_id=compute_ea4e6_router_contract_id(),
                now=clock.now_iso(),
            ),
        )
        self._invocation_count = 0
        self._max_invocations = max_invocations

    @property
    def executor_registry(self) -> ExecutorRegistry:
        return self._executor_registry

    def execute(
        self,
        request: GovernedExecutionRequest,
    ) -> GovernedProductionResult:
        """Execute the full governed production path.

        Returns structured result. Does NOT invoke real receivers.
        """
        # Step 0: Check invocation budget
        if self._invocation_count >= self._max_invocations:
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="NOT_EVALUATED",
                issuance_policy_decision="NOT_EVALUATED",
                issuance_policy_reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
                authority_issued=False,
                authority_valid=None,
                activation_issued=False,
                activation_valid=None,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason="LIVE_INVOCATION_BUDGET_EXHAUSTED",
                attempt_count=0,
            )
        self._invocation_count += 1

        # Step 1: Route
        from tools.hermes_core.receiver_router import get_default_router
        router = get_default_router()
        route_result = router.route(RoutingRequest(
            receiver_id=request.receiver_id,
            execution_authority_present=True,
        ))

        if route_result.route_decision != "SELECTED":
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision=route_result.route_decision,
                issuance_policy_decision="NOT_EVALUATED",
                issuance_policy_reason="ROUTE_NOT_SELECTED",
                authority_issued=False,
                authority_valid=None,
                activation_issued=False,
                activation_valid=None,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision=None,
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason=f"ROUTING_REJECTED:{route_result.route_reason}",
                attempt_count=0,
            )

        # Step 2: Build and evaluate issuance request
        issuance_request = ProductionIssuanceRequest(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            routing_result=route_result,
            router_contract_id=request.router_contract_id,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            delegation_class=request.delegation_class,
            requested_operation=request.requested_operation,
            requested_execution_scope=request.requested_execution_scope,
            requested_attempt_limit=request.requested_attempt_limit,
            requested_authority_ttl_seconds=request.requested_authority_ttl_seconds,
            request_nonce=f"ea4e18-{request.request_id}",
        )

        issuance_result = self._policy.evaluate(issuance_request)

        if issuance_result.policy_decision != "ELIGIBLE":
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="REJECT",
                issuance_policy_reason=issuance_result.policy_reason,
                authority_issued=issuance_result.authority_issued,
                authority_valid=issuance_result.authority_valid,
                activation_issued=issuance_result.activation_issued,
                activation_valid=issuance_result.activation_valid,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision=None,
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason=f"ISSUANCE_REJECTED:{issuance_result.policy_reason}",
                attempt_count=request.requested_attempt_limit,
            )

        # Step 3: Validate authority and activation
        if not issuance_result.authority_issued or not issuance_result.authority_valid:
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="ELIGIBLE",
                issuance_policy_reason=issuance_result.policy_reason,
                authority_issued=issuance_result.authority_issued,
                authority_valid=issuance_result.authority_valid,
                activation_issued=issuance_result.activation_issued,
                activation_valid=issuance_result.activation_valid,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision=None,
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason="AUTHORITY_INVALID",
                attempt_count=request.requested_attempt_limit,
            )

        if not issuance_result.activation_issued or not issuance_result.activation_valid:
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="ELIGIBLE",
                issuance_policy_reason=issuance_result.policy_reason,
                authority_issued=True,
                authority_valid=True,
                activation_issued=issuance_result.activation_issued,
                activation_valid=issuance_result.activation_valid,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision=None,
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason="ACTIVATION_INVALID",
                attempt_count=request.requested_attempt_limit,
            )

        # Step 4: Build execution request
        task_payload = request.task_payload or f"Return exactly: EA4E18_{request.receiver_id.upper()}_GOVERNED_EXECUTION_OK"
        execution_request = ProductionExecutionRequest(
            receiver_id=request.receiver_id,
            delegation_id=f"ea4e18-delegation-{request.request_id}",
            router_contract_id=request.router_contract_id,
            authority_contract_id=compute_ea4e7_authority_contract_id(),
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            execution_scope=request.requested_execution_scope,
            task_payload=task_payload,
            attempt_limit=request.requested_attempt_limit,
        )

        # Step 5: Execute through boundary
        exec_result = self._boundary.execute(
            receiver_id=request.receiver_id,
            authority=issuance_result.authority,
            activation=issuance_result.activation,
            execution_request=execution_request,
        )

        return GovernedProductionResult(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            route_decision="SELECTED",
            issuance_policy_decision="ELIGIBLE",
            issuance_policy_reason="POLICY_ELIGIBLE",
            authority_issued=True,
            authority_valid=True,
            activation_issued=True,
            activation_valid=True,
            execution_request_created=True,
            adapter_resolution=exec_result.adapter_resolution,
            execution_decision=exec_result.execution_decision,
            executor_called=exec_result.executor_called,
            execution_status=exec_result.execution_status,
            execution_output=exec_result.executor_output,
            reason=exec_result.reason,
            attempt_count=request.requested_attempt_limit,
        )


# --------------------------------------------------------------------------- #
# Integration contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e18_integration_contract_id() -> str:
    """Compute the deterministic EA-4E.18 integration contract ID."""
    canonical = {
        "schema_id": INTEGRATION_SCHEMA_ID,
        "schema_version": INTEGRATION_SCHEMA_VERSION,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "activation_contract_id": compute_ea4e11_activation_contract_id(),
        "execution_contract_id": compute_ea4e14_execution_contract_id(),
        "issuance_contract_id": compute_ea4e17_issuance_contract_id(),
        "qualified_receivers": {
            k: {
                "transport_contract_id": v["transport_contract_id"],
                "model_binding_id": v["model_binding_id"],
            }
            for k, v in sorted(QUALIFIED_RECEIVERS.items())
        },
        "allowed_operation": "receiver-dispatch",
        "allowed_execution_scope": "production",
        "allowed_delegation_class": "governed",
        "max_attempt_limit": 1,
        "default_issuance_decision": "DENY",
        "default_activation_state": "DISABLED",
        "real_executor_default_state": "NO",
        "retry_policy": "DISABLED",
        "fallback_policy": "DISABLED",
        "failover_policy": "DISABLED",
    }
    return sha256_payload(canonical)
