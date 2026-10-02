"""EA-4E.36 non-live production entry point.

ENABLE != EXECUTE.

Application-facing facade over the EA-4E.35 composition root. Defaults remain
disabled. One request may be explicitly activated without persisting enablement
and without invoking a real receiver or model.

The entry point does not:
- manufacture execution authority;
- issue invocation authorization itself;
- bind executors automatically;
- initialize a missing durable store;
- select a default receiver;
- route to Grok;
- retry, fall back, or fail over.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_activation import ProductionActivation
from tools.hermes_core.governed_production_caller import (
    GovernedProductionCallerRequest,
    GovernedProductionCallerResult,
)
from tools.hermes_core.governed_production_runtime import GovernedProductionRuntimeRequest
from tools.hermes_core.kilo_adapter import PINNED_KILO_PATH
from tools.hermes_core.opencode_adapter import PINNED_OPENCODE_PATH
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_wiring import (
    ProductionComposition,
    ProductionWiringError,
    classify_receiver,
    verify_frozen_executor_paths,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import DispatchAuthority


@dataclass(frozen=True)
class ProductionEntryPointRequest:
    request_id: str
    receiver_id: str | None
    task_payload: str | None = None
    production_activation_explicit: bool = False
    runtime_scope: str = "production"
    nonce: str = ""
    transport_contract_id: str | None = None
    model_binding_id: str | None = None
    authorization_issue_request: ProductionInvocationAuthorizationIssueRequest | None = None
    execution_authority: DispatchAuthority | None = None
    activation: ProductionActivation | None = None


@dataclass
class ProductionEntryPointResult:
    entrypoint_decision: str
    entrypoint_reason: str
    route_decision: str = "NOT_EVALUATED"
    activation_attempted: bool = False
    binding_attempted: bool = False
    invocation_authorization_issued: bool = False
    executor_resolution_attempted: bool = False
    caller_result: GovernedProductionCallerResult | None = None


class ProductionEntryPoint:
    """Explicit-enablement production facade. Master enable is checked first."""

    def __init__(self, composition: ProductionComposition) -> None:
        verify_frozen_executor_paths(composition.config)
        self._composition = composition

    @property
    def master_enable(self) -> str:
        return self._composition.config.master_enable

    def handle(self, request: ProductionEntryPointRequest) -> ProductionEntryPointResult:
        if self._composition.config.master_enable != "ENABLED":
            return self._deny("PRODUCTION_MASTER_ENABLE_DISABLED")
        if not request.production_activation_explicit:
            return self._deny("PRODUCTION_ACTIVATION_NOT_EXPLICIT")
        if not request.request_id or not str(request.request_id).strip():
            return self._deny("REQUEST_ID_REQUIRED")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if self._composition.config.kilo_executable_path != PINNED_KILO_PATH:
            return self._deny("EXECUTABLE_BINDING_MISMATCH")
        if self._composition.config.opencode_executable_path != PINNED_OPENCODE_PATH:
            return self._deny("EXECUTABLE_BINDING_MISMATCH")

        receiver_id = str(request.receiver_id)
        route = self._composition.router.route(RoutingRequest(receiver_id=receiver_id))
        if route.route_decision != "SELECTED":
            return ProductionEntryPointResult(
                entrypoint_decision="DENY",
                entrypoint_reason=route.route_reason,
                route_decision=route.route_decision,
            )

        handle = self._composition.binding_controller.get_binding_for_receiver(receiver_id)
        if handle is None:
            return ProductionEntryPointResult(
                entrypoint_decision="DENY",
                entrypoint_reason="MISSING_BINDING_ENABLEMENT",
                route_decision="SELECTED",
                activation_attempted=True,
            )

        issue_request = request.authorization_issue_request
        if issue_request is None:
            return ProductionEntryPointResult(
                entrypoint_decision="DENY",
                entrypoint_reason="MISSING_INVOCATION_AUTHORIZATION",
                route_decision="SELECTED",
                activation_attempted=True,
                binding_attempted=True,
            )
        if issue_request.receiver_id != receiver_id:
            return ProductionEntryPointResult(
                entrypoint_decision="DENY",
                entrypoint_reason="POST_ACTIVATION_RECEIVER_MUTATION",
                route_decision="SELECTED",
                activation_attempted=True,
                binding_attempted=True,
            )
        if issue_request.execution_request_id != request.request_id:
            return ProductionEntryPointResult(
                entrypoint_decision="DENY",
                entrypoint_reason="REQUEST_ID_MISMATCH",
                route_decision="SELECTED",
                activation_attempted=True,
                binding_attempted=True,
            )

        frozen = QUALIFIED_RECEIVERS[receiver_id]
        transport = request.transport_contract_id or frozen["transport_contract_id"]
        model = request.model_binding_id or frozen["model_binding_id"]
        runtime_request = GovernedProductionRuntimeRequest(
            request_id=request.request_id,
            receiver_id=receiver_id,
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id=transport,
            model_binding_id=model,
            task_payload=request.task_payload,
            execution_authority=request.execution_authority,
            activation=request.activation,
        )
        caller_result = self._composition.caller.invoke(
            GovernedProductionCallerRequest(runtime_request, issue_request)
        )
        decision = "ALLOW" if caller_result.caller_decision == "EXECUTED" else "DENY"
        return ProductionEntryPointResult(
            entrypoint_decision=decision,
            entrypoint_reason=caller_result.caller_reason,
            route_decision="SELECTED",
            activation_attempted=True,
            binding_attempted=True,
            invocation_authorization_issued=caller_result.issuance_decision == "ALLOW",
            executor_resolution_attempted=caller_result.resolution_decision == "RESOLVED",
            caller_result=caller_result,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionEntryPointResult:
        return ProductionEntryPointResult(
            entrypoint_decision="DENY",
            entrypoint_reason=reason,
            activation_attempted=False,
            binding_attempted=False,
            invocation_authorization_issued=False,
            executor_resolution_attempted=False,
        )


def build_production_entrypoint(composition: ProductionComposition) -> ProductionEntryPoint:
    if composition.config.default_receiver != "NONE":
        raise ProductionWiringError("DEFAULT_RECEIVER_FORBIDDEN")
    return ProductionEntryPoint(composition)
