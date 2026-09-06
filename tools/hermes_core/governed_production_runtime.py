"""EA-4E.26 dual-receiver governed production runtime integration.

This module establishes one permanent governed production-runtime entrypoint
that can consume either explicitly selected qualified receiver while
preserving every existing governance boundary:

    explicit receiver
    -> router
    -> issuance
    -> authority validation
    -> activation validation
    -> EA-4E.21 pre-existing binding check
    -> EA-4E.22 bound-executor resolution
    -> EA-4E.23 invocation authorization
    -> atomic single-use claim
    -> production execution boundary
    -> fake executor (qualification)
    -> teardown

This is a NON-LIVE qualification: no real receiver process is started.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_activation import ProductionActivationValidator
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingHandle,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    QUALIFIED_RECEIVERS,
    compute_ea4e21_binding_contract_id,
)
from tools.hermes_core.production_execution import (
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
    compute_ea4e14_execution_contract_id,
)
from tools.hermes_core.governed_bound_executor import (
    GovernedBoundExecutorResolver,
    compute_ea4e22_integration_contract_id,
)
from tools.hermes_core.governed_production import compute_ea4e18_integration_contract_id
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
    ProductionInvocationAuthorizationPolicy,
    compute_ea4e23_invocation_contract_id,
)
from tools.hermes_core.production_issuance import (
    ClockCollaborator,
    ProductionIssuancePolicy,
    ProductionIssuanceRequest,
    compute_ea4e17_issuance_contract_id,
)
from tools.hermes_core.receiver_dispatch import ExecutionAuthorityValidator
from tools.hermes_core.receiver_router import (
    RoutingRequest,
    get_default_router,
    compute_ea4e6_router_contract_id,
)



# --------------------------------------------------------------------------- #
# Integration schema
# --------------------------------------------------------------------------- #

INTEGRATION_SCHEMA_ID = "hermes.dual-receiver-governed-production-runtime/v1"
INTEGRATION_SCHEMA_VERSION = "ea4e.26"
INTEGRATION_ARTIFACT_VERSION = "1"

# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# --------------------------------------------------------------------------- #
# Runtime request
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GovernedProductionRuntimeRequest:
    """Explicit request for the dual-receiver governed production runtime.

    The receiver must be explicitly selected. No inference is performed.
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
    invocation_authorization: ProductionInvocationAuthorization | None = None


# --------------------------------------------------------------------------- #
# Runtime result
# --------------------------------------------------------------------------- #

@dataclass
class GovernedProductionRuntimeResult:
    """Structured result of the EA-4E.26 dual-receiver governed runtime path."""
    request_id: str = ""
    receiver_id: str = ""

    # Governance path decisions
    route_decision: str = "NOT_EVALUATED"
    issuance_policy_decision: str = "NOT_EVALUATED"
    authority_valid: bool = False
    activation_valid: bool = False
    binding_decision: str = "NOT_EVALUATED"
    binding_reason: str = ""
    ea4e22_resolution_decision: str = "NOT_EVALUATED"
    ea4e22_resolution_reason: str = ""
    invocation_claim_decision: str = "NOT_EVALUATED"
    invocation_claim_reason: str = ""
    execution_decision: str = "NOT_EVALUATED"

    # Bypass tracking (all default True = bypassed, set False when actually evaluated)
    router_bypassed: bool = True
    issuance_bypassed: bool = True
    authority_validation_bypassed: bool = True
    activation_validation_bypassed: bool = True
    binding_check_bypassed: bool = True
    ea4e22_resolution_bypassed: bool = True
    invocation_authorization_bypassed: bool = True
    atomic_claim_bypassed: bool = True
    production_boundary_bypassed: bool = True

    # Execution
    executor_called: bool = False
    executor_id: Optional[str] = None
    execution_status: Optional[str] = None
    execution_output: Optional[str] = None

    # Accounting
    kilo_executor_calls: int = 0
    opencode_executor_calls: int = 0
    real_kilo_executor_instantiations: int = 0
    real_opencode_executor_instantiations: int = 0
    real_kilo_adapter_calls: int = 0
    real_opencode_adapter_calls: int = 0
    live_bindings_created: int = 0
    live_invocation_authorizations_issued: int = 0
    live_invocation_authorization_claims_granted: int = 0
    live_dispatch_executions: int = 0
    production_execution_boundary_real_executions: int = 0
    automatic_retry_attempts: int = 0
    fallback_attempts: int = 0
    failover_attempts: int = 0

    # Default state
    default_binding_decision: str = "DENY"
    default_invocation_authorization_decision: str = "DENY"
    default_receiver: str = "NONE"
    automatic_receiver_selection_enabled: bool = False
    automatic_executor_binding_enabled: bool = False
    automatic_invocation_authorization_enabled: bool = False
    automatic_retry_enabled: bool = False
    fallback_enabled: bool = False
    failover_enabled: bool = False
    production_activation_default: str = "DISABLED"
    persistent_production_execution_enabled: bool = False

    # Final
    ea4e26_disposition: str = "HOLD"
    reason: str = ""


# --------------------------------------------------------------------------- #
# Runtime coordinator
# --------------------------------------------------------------------------- #

class GovernedProductionRuntime:
    """Dual-receiver governed production runtime coordinator.

    Composes the already-qualified boundaries into one permanent entrypoint.
    Requires explicit receiver selection. Requires pre-existing binding.
    Requires explicit invocation authorization. No auto-bind. No fallback.
    """

    def __init__(
        self,
        *,
        clock: ClockCollaborator,
        executor_registry: Optional[ExecutorRegistry] = None,
        binding_controller: Optional[ProductionExecutorBindingController] = None,
        max_invocations: int = 1,
    ) -> None:
        self._clock = clock
        self._executor_registry = executor_registry or ExecutorRegistry()
        self._binding_controller = binding_controller or ProductionExecutorBindingController(
            policy=ProductionExecutorBindingPolicy(clock=BindingClock(now=clock.now_iso())),
            clock=BindingClock(now=clock.now_iso()),
        )
        self._resolver = GovernedBoundExecutorResolver(
            binding_controller=self._binding_controller,
            executor_registry=self._executor_registry,
            clock=BindingClock(now=clock.now_iso()),
        )
        self._invocation_policy = ProductionInvocationAuthorizationPolicy(clock=clock)
        self._boundary = ProductionExecutionBoundary(
            executor_registry=self._executor_registry,
            authority_validator=ExecutionAuthorityValidator(
                router_contract_id=compute_ea4e6_router_contract_id(),
                now=clock.now_iso(),
            ),
            activation_validator=ProductionActivationValidator(
                router_contract_id=compute_ea4e6_router_contract_id(),
            ),
        )
        self._invocation_count = 0
        self._max_invocations = max_invocations

    @property
    def binding_controller(self) -> ProductionExecutorBindingController:
        return self._binding_controller

    @property
    def executor_registry(self) -> ExecutorRegistry:
        return self._executor_registry

    def execute(
        self,
        request: GovernedProductionRuntimeRequest,
    ) -> GovernedProductionRuntimeResult:
        """Execute the full dual-receiver governed production runtime path.

        Returns structured result. Does NOT invoke real receivers.
        """
        result = GovernedProductionRuntimeResult(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
        )

        # Step 1: Route (explicit receiver required)
        router = get_default_router()
        route_result = router.route(RoutingRequest(
            receiver_id=request.receiver_id,
            execution_authority_present=True,
        ))

        if route_result.route_decision != "SELECTED":
            result.route_decision = route_result.route_decision
            result.reason = f"ROUTING_REJECTED:{route_result.route_reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.route_decision = "SELECTED"
        result.router_bypassed = False

        # Step 2: Issuance
        issuance_policy = ProductionIssuancePolicy(clock=self._clock)
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
            request_nonce=f"ea4e26-{request.request_id}",
        )
        issuance_result = issuance_policy.evaluate(issuance_request)

        if issuance_result.policy_decision != "ELIGIBLE":
            result.issuance_policy_decision = issuance_result.policy_decision
            result.reason = f"ISSUANCE_REJECTED:{issuance_result.policy_reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.issuance_policy_decision = "ELIGIBLE"
        result.issuance_bypassed = False

        # Step 3: Authority validation
        authority_result = self._boundary._authority_validator.validate(
            issuance_result.authority, route_result,
        )
        if authority_result.dispatch_decision != "AUTHORIZED":
            result.authority_valid = False
            result.reason = f"AUTHORITY_REJECTED:{authority_result.reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.authority_valid = True
        result.authority_validation_bypassed = False

        # Step 4: Activation validation
        activation_result = self._boundary._activation_validator.validate(
            issuance_result.activation, receiver_id=request.receiver_id,
        )
        if activation_result.dispatch_decision != "AUTHORIZED":
            result.activation_valid = False
            result.reason = f"ACTIVATION_REJECTED:{activation_result.reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.activation_valid = True
        result.activation_validation_bypassed = False

        # Step 5: Pre-existing binding check (EA-4E.21)
        handle = self._binding_controller.get_binding_for_receiver(request.receiver_id)
        if handle is None:
            result.binding_decision = "REJECT"
            result.binding_reason = "NO_ACTIVE_EXECUTOR_BINDING"
            result.reason = "NO_ACTIVE_EXECUTOR_BINDING"
            result.ea4e26_disposition = "FAIL"
            return result

        # Verify receiver match
        if handle.receiver_id != request.receiver_id:
            result.binding_decision = "REJECT"
            result.binding_reason = "RECEIVER_BINDING_MISMATCH"
            result.reason = "RECEIVER_BINDING_MISMATCH"
            result.ea4e26_disposition = "FAIL"
            return result

        result.binding_decision = "ALLOW"
        result.binding_check_bypassed = False

        # Step 6: EA-4E.22 bound-executor resolution
        ea4e22_result = self._resolver.resolve_governed_executor(request.receiver_id)

        if ea4e22_result.resolution_decision != "RESOLVED":
            result.ea4e22_resolution_decision = ea4e22_result.resolution_decision
            result.ea4e22_resolution_reason = ea4e22_result.resolution_reason
            result.reason = f"EA4E22_RESOLUTION_FAILED:{ea4e22_result.resolution_reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.ea4e22_resolution_decision = "RESOLVED"
        result.ea4e22_resolution_reason = ea4e22_result.resolution_reason
        result.ea4e22_resolution_bypassed = False

        # Step 7: EA-4E.23 invocation authorization must be supplied by the caller.
        invocation_auth = request.invocation_authorization
        result.invocation_authorization_bypassed = False
        if invocation_auth is None:
            result.invocation_claim_decision = "DENY"
            result.invocation_claim_reason = "INVOCATION_AUTHORIZATION_REQUIRED"
            result.reason = "CLAIM_REJECTED:INVOCATION_AUTHORIZATION_REQUIRED"
            result.ea4e26_disposition = "FAIL"
            return result

        # Step 8: Atomic claim
        bound_meta = {}
        claim_result = self._invocation_policy.claim_for_execution(
            invocation_auth,
            handle,
            bound_meta,
            expected_execution_request_id=request.request_id,
        )

        result.invocation_claim_decision = claim_result.policy_decision
        result.invocation_claim_reason = claim_result.policy_reason
        result.atomic_claim_bypassed = False

        if not claim_result.binding_authorized:
            result.reason = f"CLAIM_REJECTED:{claim_result.policy_reason}"
            result.ea4e26_disposition = "FAIL"
            return result

        result.live_invocation_authorization_claims_granted = 1

        # Step 8b: Check invocation budget (after claim, so pre-execution rejections don't consume)
        if self._invocation_count >= self._max_invocations:
            result.reason = "INVOCATION_BUDGET_EXHAUSTED"
            result.ea4e26_disposition = "FAIL"
            return result
        self._invocation_count += 1

        # Step 9: Production execution through boundary
        # Use exact deterministic output marker per receiver
        if request.task_payload:
            task_payload = request.task_payload
        elif request.receiver_id == "kilo-cli-agent":
            task_payload = "EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK"
        elif request.receiver_id == "opencode-cli-agent":
            task_payload = "EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK"
        else:
            task_payload = "UNREACHABLE"
        execution_request = ProductionExecutionRequest(
            receiver_id=request.receiver_id,
            delegation_id=f"ea4e26-delegation-{request.request_id}",
            router_contract_id=request.router_contract_id,
            authority_contract_id="placeholder",
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            execution_scope=request.requested_execution_scope,
            task_payload=task_payload,
            attempt_limit=request.requested_attempt_limit,
        )

        exec_result = self._boundary.execute(
            receiver_id=request.receiver_id,
            authority=issuance_result.authority,
            activation=issuance_result.activation,
            execution_request=execution_request,
        )

        result.production_boundary_bypassed = False
        result.live_dispatch_executions = 1
        result.executor_called = exec_result.executor_called
        result.executor_id = exec_result.executor_id
        result.execution_decision = exec_result.execution_decision
        result.execution_status = exec_result.execution_status
        result.execution_output = exec_result.executor_output

        # Step 10: Receiver-specific accounting
        if request.receiver_id == "kilo-cli-agent":
            result.kilo_executor_calls = 1 if exec_result.executor_called else 0
        elif request.receiver_id == "opencode-cli-agent":
            result.opencode_executor_calls = 1 if exec_result.executor_called else 0

        result.ea4e26_disposition = "PASS"
        result.reason = "GOVERNED_EXECUTION_OK"
        return result


# --------------------------------------------------------------------------- #
# Integration contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e26_integration_contract_id() -> str:
    """Compute the deterministic EA-4E.26 integration contract ID."""
    canonical = {
        "schema_id": INTEGRATION_SCHEMA_ID,
        "schema_version": INTEGRATION_SCHEMA_VERSION,
        "artifact_version": INTEGRATION_ARTIFACT_VERSION,
        "ea4e14_execution_contract_id": compute_ea4e14_execution_contract_id(),
        "ea4e17_issuance_contract_id": compute_ea4e17_issuance_contract_id(),
        "ea4e18_integration_contract_id": compute_ea4e18_integration_contract_id(),
        "ea4e21_binding_contract_id": compute_ea4e21_binding_contract_id(),
        "ea4e22_integration_contract_id": compute_ea4e22_integration_contract_id(),
        "ea4e23_invocation_contract_id": compute_ea4e23_invocation_contract_id(),
        "qualified_receivers": {
            k: {
                "transport_contract_id": v["transport_contract_id"],
                "model_binding_id": v["model_binding_id"],
            }
            for k, v in sorted(QUALIFIED_RECEIVERS.items())
        },
        "explicit_receiver_required": True,
        "preexisting_binding_required": True,
        "no_auto_bind": True,
        "ea4e22_resolution_required": True,
        "invocation_authorization_required": True,
        "atomic_claim_required": True,
        "max_invocation_auth_ttl_seconds": 300,
        "max_authorized_attempts": 1,
        "default_invocation_authorization": "DENY",
        "default_receiver": "NONE",
        "automatic_retry_disabled": True,
        "fallback_disabled": True,
        "failover_disabled": True,
        "production_runtime_default": "DISABLED",
        "persistent_production_execution_disabled": True,
        "fake_qualification_only": True,
    }
    return sha256_payload(canonical)
