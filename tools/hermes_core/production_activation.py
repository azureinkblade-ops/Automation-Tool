"""EA-4E.11 dual-receiver production activation boundary.

This module establishes the production activation gate and receiver resolver
for the two qualified receivers: Kilo and OpenCode.

The logical flow is:

    ProductionDispatchRequest
    → ReceiverRouter (EA-4E.6)
    → RoutingResult
    → ExecutionAuthorityValidator (EA-4E.7)
    → DispatchDecision
    → ProductionActivationValidator (EA-4E.11)
    → ReceiverAdapterResolver (EA-4E.11)
    → fake/inert adapter boundary
    → NO PROCESS START

Core invariants:
    ROUTING != AUTHORIZATION != ACTIVATION != EXECUTION
    Default: PRODUCTION_ACTIVATION=DISABLED
    No fallback/failover.
    No automatic receiver selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    ReceiverRouter,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    ExecutionAuthorityValidator,
    compute_ea4e7_authority_contract_id,
)


# --------------------------------------------------------------------------- #
# Activation schema
# --------------------------------------------------------------------------- #

ACTIVATION_SCHEMA_ID = "hermes.production-activation.receiver-dispatch/v1"
ACTIVATION_SCHEMA_VERSION = "ea4e.11"
ACTIVATION_ARTIFACT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Production activation contract
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionActivation:
    """Explicit production activation decision.

    This is a separate boundary from execution authority.
    Authorization grants permission to dispatch.
    Activation grants permission to cross into production execution.
    """
    activation_id: str
    artifact_version: str
    artifact_hash: str
    receiver_id: str
    router_contract_id: str
    authority_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    activation_mode: str  # "ENABLED" or "DISABLED"
    execution_scope: str
    delegation_class: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "artifact_version": self.artifact_version,
            "receiver_id": self.receiver_id,
            "router_contract_id": self.router_contract_id,
            "authority_contract_id": self.authority_contract_id,
            "transport_contract_id": self.transport_contract_id,
            "model_binding_id": self.model_binding_id,
            "activation_mode": self.activation_mode,
            "execution_scope": self.execution_scope,
            "delegation_class": self.delegation_class,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


def _derive_activation_id(preimage: dict[str, Any]) -> str:
    return "production-activation-" + sha256_payload(preimage)[:16]


def build_production_activation(
    *,
    receiver_id: str,
    router_contract_id: str,
    authority_contract_id: str,
    transport_contract_id: str,
    model_binding_id: str,
    activation_mode: str,
    execution_scope: str,
    delegation_class: str,
) -> ProductionActivation:
    """Build a production activation artifact.

    This is the ONLY way to create production activation.
    Default mode is DISABLED.
    """
    if activation_mode not in ("ENABLED", "DISABLED"):
        raise ValueError(f"Invalid activation_mode: {activation_mode}")

    preimage = {
        "artifact_version": ACTIVATION_ARTIFACT_VERSION,
        "receiver_id": receiver_id,
        "router_contract_id": router_contract_id,
        "authority_contract_id": authority_contract_id,
        "transport_contract_id": transport_contract_id,
        "model_binding_id": model_binding_id,
        "activation_mode": activation_mode,
        "execution_scope": execution_scope,
        "delegation_class": delegation_class,
    }
    activation_id = _derive_activation_id(preimage)
    full = {**preimage, "activation_id": activation_id}
    artifact_hash = sha256_payload(full)
    return ProductionActivation(
        activation_id=activation_id,
        artifact_version=ACTIVATION_ARTIFACT_VERSION,
        artifact_hash=artifact_hash,
        receiver_id=receiver_id,
        router_contract_id=router_contract_id,
        authority_contract_id=authority_contract_id,
        transport_contract_id=transport_contract_id,
        model_binding_id=model_binding_id,
        activation_mode=activation_mode,
        execution_scope=execution_scope,
        delegation_class=delegation_class,
    )


# --------------------------------------------------------------------------- #
# Production activation validator
# --------------------------------------------------------------------------- #

class ProductionActivationValidator:
    """Validates production activation artifacts.

    Fail-closed: any mismatch rejects activation.
    """

    def __init__(
        self,
        *,
        router_contract_id: str,
        qualified_receivers: Optional[dict[str, dict[str, str]]] = None,
    ) -> None:
        self._router_contract_id = router_contract_id
        self._qualified = qualified_receivers or QUALIFIED_RECEIVERS

    def validate(
        self,
        activation: Optional[ProductionActivation],
        *,
        receiver_id: str,
    ) -> "ActivationResult":
        """Validate production activation.

        Returns ActivationResult with activation_valid=True only if all gates pass.
        """
        # Gate 1: Activation must be present
        if activation is None:
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="PRODUCTION_ACTIVATION_MISSING",
            )

        # Gate 2: Activation must be ENABLED
        if activation.activation_mode != "ENABLED":
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="PRODUCTION_ACTIVATION_DISABLED",
            )

        # Gate 3: Receiver must match
        if activation.receiver_id != receiver_id:
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="ACTIVATION_RECEIVER_MISMATCH",
            )

        # Gate 4: Router contract must match
        if activation.router_contract_id != self._router_contract_id:
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="ROUTER_CONTRACT_MISMATCH",
            )

        # Gate 5: Authority contract must match
        if activation.authority_contract_id != compute_ea4e7_authority_contract_id():
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="AUTHORITY_CONTRACT_MISMATCH",
            )

        # Gate 6: Transport contract must match frozen value
        expected_transport = self._qualified.get(receiver_id, {}).get(
            "transport_contract_id", ""
        )
        if activation.transport_contract_id != expected_transport:
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="TRANSPORT_CONTRACT_MISMATCH",
            )

        # Gate 7: Model binding must match frozen value
        expected_model = self._qualified.get(receiver_id, {}).get(
            "model_binding_id", ""
        )
        if activation.model_binding_id != expected_model:
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="MODEL_BINDING_MISMATCH",
            )

        # Gate 8: Activation hash must verify
        if not activation.verify_hash():
            return ActivationResult(
                activation_valid=False,
                dispatch_decision="REJECT",
                reason="MALFORMED_ACTIVATION",
            )

        return ActivationResult(
            activation_valid=True,
            dispatch_decision="AUTHORIZED",
            reason="ACTIVATION_VALID",
        )


@dataclass(frozen=True)
class ActivationResult:
    """Result of production activation validation."""
    activation_valid: bool
    dispatch_decision: str
    reason: str


# --------------------------------------------------------------------------- #
# Receiver adapter resolver
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ResolvedAdapter:
    """Result of receiver adapter resolution."""
    receiver_id: str
    adapter_kind: str
    adapter_factory: Callable[[], Any]


class ReceiverAdapterResolver:
    """Maps qualified receivers to adapter factories.

    No default receiver. No automatic selection. No fallback.
    """

    def __init__(
        self,
        *,
        qualified_receivers: Optional[dict[str, dict[str, str]]] = None,
    ) -> None:
        self._qualified = qualified_receivers or QUALIFIED_RECEIVERS
        self._adapter_map: dict[str, Callable[[], Any]] = {
            "opencode-cli-agent": self._create_opencode_adapter,
            "kilo-cli-agent": self._create_kilo_adapter,
        }

    def _create_opencode_adapter(self):
        """Create a fake/inert OpenCode adapter for qualification."""
        from tools.hermes_core.opencode_adapter import OpenCodeFakeProcess, OpenCodeReceiverAdapter
        return OpenCodeReceiverAdapter(process_impl=OpenCodeFakeProcess())

    def _create_kilo_adapter(self):
        """Create a fake/inert Kilo adapter for qualification."""
        from tools.hermes_core.kilo_adapter import KiloAdapter
        return KiloAdapter(config={})

    def resolve(self, receiver_id: str) -> ResolvedAdapter:
        """Resolve receiver to adapter factory.

        Returns ResolvedAdapter or raises ValueError for unsupported receivers.
        """
        if receiver_id not in self._qualified:
            raise ValueError(f"UNSUPPORTED_RECEIVER: {receiver_id}")

        factory = self._adapter_map.get(receiver_id)
        if factory is None:
            raise ValueError(f"ADAPTER_NOT_CONFIGURED: {receiver_id}")

        adapter_kind = self._qualified[receiver_id].get("receiver_class", "UNKNOWN")
        return ResolvedAdapter(
            receiver_id=receiver_id,
            adapter_kind=adapter_kind,
            adapter_factory=factory,
        )


# --------------------------------------------------------------------------- #
# Production receiver coordinator
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionDispatchResult:
    """Result of production-path dispatch."""
    receiver_id: Optional[str]
    route_decision: str
    authority_valid: bool
    activation_valid: bool
    dispatch_decision: str
    adapter_resolution: Optional[str]
    production_path_integration: str
    real_adapter_called: bool = False
    process_started: bool = False
    model_invoked: bool = False
    receiver_executed: bool = False
    reason: str = ""


class ProductionReceiverCoordinator:
    """Production-path coordinator for dual-receiver dispatch.

    Orchestrates:
    1. ReceiverRouter (EA-4E.6)
    2. ExecutionAuthorityValidator (EA-4E.7)
    3. ProductionActivationValidator (EA-4E.11)
    4. ReceiverAdapterResolver (EA-4E.11)
    5. Fake adapter boundary (NO PROCESS START)
    """

    COORDINATOR_SCHEMA_ID = "hermes.production-receiver.coordinator/v1"
    COORDINATOR_SCHEMA_VERSION = "ea4e.11"

    def __init__(
        self,
        *,
        router: Optional[ReceiverRouter] = None,
        activation_validator: Optional[ProductionActivationValidator] = None,
        adapter_resolver: Optional[ReceiverAdapterResolver] = None,
    ) -> None:
        self._router = router or get_default_router()
        self._authority_validator = ExecutionAuthorityValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._activation_validator = activation_validator or ProductionActivationValidator(
            router_contract_id=self._router.get_contract_id(),
        )
        self._adapter_resolver = adapter_resolver or ReceiverAdapterResolver()

    def dispatch(
        self,
        *,
        receiver_id: str,
        authority: Optional[DispatchAuthority],
        activation: Optional[ProductionActivation],
        delegation_class: str = "governed",
    ) -> ProductionDispatchResult:
        """Execute the full production dispatch flow.

        NEVER starts a process. NEVER invokes a model.
        """
        # Step 1: Route selection
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        if route_result.route_decision != "SELECTED":
            return ProductionDispatchResult(
                receiver_id=None,
                route_decision=route_result.route_decision,
                authority_valid=False,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                production_path_integration="PASS",
                reason=route_result.route_reason,
            )

        # Step 2: Authority validation
        authority_result = self._authority_validator.validate(authority, route_result)
        if authority_result.dispatch_decision != "AUTHORIZED":
            return ProductionDispatchResult(
                receiver_id=receiver_id,
                route_decision=authority_result.route_decision,
                authority_valid=authority_result.authority_valid,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                production_path_integration="PASS",
                reason=authority_result.reason,
            )

        # Step 3: Activation validation
        activation_result = self._activation_validator.validate(
            activation, receiver_id=receiver_id
        )
        if activation_result.dispatch_decision != "AUTHORIZED":
            return ProductionDispatchResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=False,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                production_path_integration="PASS",
                reason=activation_result.reason,
            )

        # Step 4: Adapter resolution
        try:
            resolved = self._adapter_resolver.resolve(receiver_id)
        except ValueError as e:
            return ProductionDispatchResult(
                receiver_id=receiver_id,
                route_decision="SELECTED",
                authority_valid=True,
                activation_valid=True,
                dispatch_decision="REJECT",
                adapter_resolution=None,
                production_path_integration="PASS",
                reason=str(e),
            )

        # Step 5: Fake adapter boundary (NO PROCESS START)
        # In production, this would call the real adapter.
        # For qualification, we use the fake adapter and do NOT execute.
        adapter = resolved.adapter_factory()
        # DO NOT call adapter.execute() — this is the inert boundary.

        return ProductionDispatchResult(
            receiver_id=receiver_id,
            route_decision="SELECTED",
            authority_valid=True,
            activation_valid=True,
            dispatch_decision="AUTHORIZED",
            adapter_resolution=resolved.adapter_kind,
            production_path_integration="PASS",
            real_adapter_called=False,
            process_started=False,
            model_invoked=False,
            receiver_executed=False,
            reason="PRODUCTION_PATH_COMPLETE",
        )


# --------------------------------------------------------------------------- #
# Canonical material
# --------------------------------------------------------------------------- #

def get_activation_canonical_material() -> dict[str, Any]:
    """Return deterministic canonical material for EA-4E.11 activation contract."""
    return {
        "schema_id": ACTIVATION_SCHEMA_ID,
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "artifact_version": ACTIVATION_ARTIFACT_VERSION,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "qualified_receivers": {
            k: QUALIFIED_RECEIVERS[k] for k in sorted(QUALIFIED_RECEIVERS)
        },
        "activation_default": "DISABLED",
        "fail_closed_behaviors": [
            "PRODUCTION_ACTIVATION_MISSING",
            "PRODUCTION_ACTIVATION_DISABLED",
            "ACTIVATION_RECEIVER_MISMATCH",
            "ROUTER_CONTRACT_MISMATCH",
            "AUTHORITY_CONTRACT_MISMATCH",
            "TRANSPORT_CONTRACT_MISMATCH",
            "MODEL_BINDING_MISMATCH",
            "MALFORMED_ACTIVATION",
            "UNSUPPORTED_RECEIVER",
            "ADAPTER_NOT_CONFIGURED",
        ],
        "execution_boundary": {
            "router_creates_execution_authority": False,
            "activation_gate_creates_execution_authority": False,
            "production_coordinator_creates_execution_authority": False,
            "router_starts_receiver": False,
            "authority_validator_starts_receiver": False,
            "activation_validator_starts_receiver": False,
            "adapter_resolver_starts_receiver": False,
            "qualification_fake_adapter_starts_receiver": False,
        },
    }


def compute_ea4e11_activation_contract_id() -> str:
    """Compute the canonical EA-4E.11 activation contract ID."""
    return sha256_payload(get_activation_canonical_material())
