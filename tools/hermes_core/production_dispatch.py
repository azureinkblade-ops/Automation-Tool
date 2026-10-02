"""EA-4E.8 production-path integration boundary.

This module integrates the EA-4E.6 receiver router and EA-4E.7
execution-authority boundary into the production control path seam.

This is NON-LIVE qualification: no real receiver process is started.

The logical flow is:

    production delegation request
    → normalize routing input
    → ReceiverRouter (EA-4E.6)
    → RoutingResult
    → explicit execution authority input
    → ExecutionAuthorityValidator (EA-4E.7)
    → DispatchDecision
    → FakeDispatchLayer
    → NO PROCESS START

Preserves: ROUTING != AUTHORIZATION != EXECUTION
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    ReceiverRouter,
    RoutingRequest,
    RoutingResult,
    compute_ea4e6_router_contract_id,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    AUTHORITY_SCHEMA_ID as EA4E7_AUTHORITY_SCHEMA_ID,
    AUTHORITY_SCHEMA_VERSION as EA4E7_AUTHORITY_SCHEMA_VERSION,
    DispatchAuthority,
    DispatchAuthorityScope,
    DispatchDecision,
    ExecutionAuthorityValidator,
    FakeDispatchLayer,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
    get_authority_canonical_material,
)


# --------------------------------------------------------------------------- #
# Production dispatch request
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionDispatchRequest:
    """Production-path request for receiver dispatch.

    This is the entry point for the production control path.
    Task text is explicitly excluded from routing decisions.
    """
    receiver_id: str
    delegation_class: str = "governed"
    execution_authority: Optional[DispatchAuthority] = None
    execution_mode: str = "fake"  # "fake" | "dry_run" | "inert"


@dataclass(frozen=True)
class ProductionDispatchResult:
    """Result of production-path dispatch integration.

    ``receiver_executed`` is ALWAYS False for fake qualification.
    ``real_adapter_called`` is ALWAYS False for fake qualification.
    """
    receiver_id: Optional[str]
    route_decision: str
    authority_valid: bool
    dispatch_decision: str
    production_path_integration: str
    real_adapter_called: bool = False
    process_started: bool = False
    model_invoked: bool = False
    receiver_executed: bool = False
    reason: str = ""


# --------------------------------------------------------------------------- #
# Production dispatch coordinator
# --------------------------------------------------------------------------- #

class ReceiverDispatchCoordinator:
    """Production-path coordinator for receiver dispatch.

    Wires together:
    1. EA-4E.6 receiver router (receiver selection)
    2. EA-4E.7 authority validator (execution permission)
    3. Fake dispatch layer (inert boundary)

    NEVER starts a real receiver process. NEVER invokes a model.
    """

    COORDINATOR_SCHEMA_ID = "hermes.receiver-dispatch.coordinator/v1"
    COORDINATOR_SCHEMA_VERSION = "ea4e.8"

    def __init__(
        self,
        *,
        router: Optional[ReceiverRouter] = None,
        dispatch_layer: Optional[FakeDispatchLayer] = None,
    ) -> None:
        self._router = router or get_default_router()
        self._dispatch_layer = dispatch_layer or FakeDispatchLayer()

    def dispatch(self, request: ProductionDispatchRequest) -> ProductionDispatchResult:
        """Execute the production-path dispatch flow.

        NEVER starts a process. NEVER invokes a model.
        """
        # Step 1: Route selection (EA-4E.6)
        route_result = self._router.route(RoutingRequest(
            receiver_id=request.receiver_id,
            execution_authority_present=request.execution_authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return ProductionDispatchResult(
                receiver_id=None,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                production_path_integration="PASS",
                reason=route_result.route_reason,
            )

        # Step 2: Authority validation (EA-4E.7)
        dispatch_result = self._dispatch_layer.dispatch(
            receiver_id=request.receiver_id,
            authority=request.execution_authority,
            delegation_class=request.delegation_class,
        )

        # Step 3: Production-path result (no execution)
        return ProductionDispatchResult(
            receiver_id=dispatch_result.receiver_id,
            route_decision=dispatch_result.route_decision,
            authority_valid=dispatch_result.authority_valid,
            dispatch_decision=dispatch_result.dispatch_decision,
            production_path_integration="PASS",
            real_adapter_called=False,
            process_started=False,
            model_invoked=False,
            receiver_executed=False,
            reason=dispatch_result.reason,
        )


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #

_default_coordinator = ReceiverDispatchCoordinator()


def get_default_coordinator() -> ReceiverDispatchCoordinator:
    """Return the default production dispatch coordinator."""
    return _default_coordinator


def dispatch_via_production_path(
    receiver_id: str,
    *,
    execution_authority: Optional[DispatchAuthority] = None,
    delegation_class: str = "governed",
) -> ProductionDispatchResult:
    """Convenience wrapper around the default coordinator."""
    request = ProductionDispatchRequest(
        receiver_id=receiver_id,
        delegation_class=delegation_class,
        execution_authority=execution_authority,
    )
    return _default_coordinator.dispatch(request)


# --------------------------------------------------------------------------- #
# Canonical coordinator material
# --------------------------------------------------------------------------- #

def get_coordinator_canonical_material() -> dict[str, Any]:
    """Return deterministic canonical material for EA-4E.8 coordinator."""
    return {
        "schema_id": ReceiverDispatchCoordinator.COORDINATOR_SCHEMA_ID,
        "schema_version": ReceiverDispatchCoordinator.COORDINATOR_SCHEMA_VERSION,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "qualified_receivers": {
            k: QUALIFIED_RECEIVERS[k] for k in sorted(QUALIFIED_RECEIVERS)
        },
        "execution_mode": "fake",
        "fail_closed_behaviors": [
            "ROUTE_NOT_SELECTED",
            "EXECUTION_AUTHORITY_MISSING",
            "EXECUTION_AUTHORITY_DENIED",
            "AUTHORITY_RECEIVER_MISMATCH",
            "ROUTER_CONTRACT_MISMATCH",
            "TRANSPORT_CONTRACT_MISMATCH",
            "MODEL_BINDING_MISMATCH",
            "MALFORMED_AUTHORITY",
            "AUTHORITY_EXPIRED",
        ],
        "execution_boundary": {
            "router_creates_execution_authority": False,
            "production_integration_creates_execution_authority": False,
            "router_starts_receiver": False,
            "authority_validator_starts_receiver": False,
            "production_integration_starts_receiver": False,
            "fake_execution_boundary_starts_receiver": False,
        },
    }


def compute_ea4e8_coordinator_contract_id() -> str:
    """Compute the canonical EA-4E.8 coordinator contract ID."""
    return sha256_payload(get_coordinator_canonical_material())
