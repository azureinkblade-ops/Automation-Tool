"""EA-4E.22 governed production runtime / executor-binding integration.

This module establishes the permanent integration seam between:
1. EA-4E.21 production real-executor binding policy/controller
2. GovernedProductionCoordinator / ProductionExecutionBoundary

This is a non-live qualification: no real receiver process is started.

The runtime integration answers:
    IS THE EXPLICITLY SELECTED RECEIVER CURRENTLY BOUND
    BY A VALID EA-4E.21 RUNTIME BINDING?

It does NOT answer:
    WHICH RECEIVER SHOULD BE SELECTED?
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingHandle,
    ProductionExecutorProtocol,
    ProductionExecutorResult,
    compute_ea4e21_binding_contract_id,
    parse_iso_timestamp,
)
from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
    GovernedProductionResult,
    compute_ea4e18_integration_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_execution import (
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
    compute_ea4e14_execution_contract_id,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    compute_ea4e11_activation_contract_id,
)
from tools.hermes_core.production_issuance import (
    compute_ea4e17_issuance_contract_id,
)


# --------------------------------------------------------------------------- #
# Integration schema
# --------------------------------------------------------------------------- #

INTEGRATION_SCHEMA_ID = "hermes.governed-bound-executor-integration.receiver-dispatch/v1"
INTEGRATION_SCHEMA_VERSION = "ea4e.22"
INTEGRATION_ARTIFACT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Executor resolution result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class GovernedExecutorResolution:
    """Result of resolving a pre-bound executor for governed execution."""
    resolution_decision: str  # RESOLVED or REJECT
    resolution_reason: str
    executor: Optional[ProductionExecutorProtocol] = None
    binding_handle: Optional[ProductionExecutorBindingHandle] = None
    binding_id: Optional[str] = None
    receiver_id: Optional[str] = None
    bound_at: Optional[str] = None
    expires_at: Optional[str] = None

    @classmethod
    def success(
        cls,
        executor: ProductionExecutorProtocol,
        handle: ProductionExecutorBindingHandle,
    ) -> GovernedExecutorResolution:
        return cls(
            resolution_decision="RESOLVED",
            resolution_reason="BINDING_VALID",
            executor=executor,
            binding_handle=handle,
            binding_id=handle.binding_id,
            receiver_id=handle.receiver_id,
            bound_at=handle.bound_at,
            expires_at=handle.expires_at,
        )

    @classmethod
    def reject(cls, reason: str) -> GovernedExecutorResolution:
        return cls(
            resolution_decision="REJECT",
            resolution_reason=reason,
        )


# --------------------------------------------------------------------------- #
# Bound executor resolver
# --------------------------------------------------------------------------- #

class GovernedBoundExecutorResolver:
    """Resolves pre-bound executors for governed production runtime.

    Answers: IS THE EXPLICITLY SELECTED RECEIVER CURRENTLY BOUND
    BY A VALID EA-4E.21 RUNTIME BINDING?

    Does NOT:
    - select a receiver
    - create a binding
    - instantiate a real executor
    - execute a receiver
    - issue authority or activation
    - extend binding lifetime
    - refresh binding expiry
    - mutate EA-4E.21 replay state
    """

    def __init__(
        self,
        *,
        binding_controller: ProductionExecutorBindingController,
        executor_registry: ExecutorRegistry,
        clock: BindingClock,
    ) -> None:
        self._controller = binding_controller
        self._registry = executor_registry
        self._clock = clock

    def resolve_governed_executor(
        self,
        receiver_id: str,
    ) -> GovernedExecutorResolution:
        """Resolve a pre-bound executor for the given receiver.

        Returns the bound executor if:
        - A binding exists for the receiver
        - The binding is not expired (using injected clock)
        - The executor is registered in the registry

        Rejects otherwise.

        If the binding is expired, synchronously prunes the expired binding
        from the active ledger and unregisters the executor via the
        authoritative controller lifecycle API.
        """
        # Step 1: Find binding for this receiver
        handle = self._controller.get_binding_for_receiver(receiver_id)
        if handle is None:
            return GovernedExecutorResolution.reject("EXECUTOR_NOT_BOUND")

        # Step 2: Verify receiver match (explicit)
        if handle.receiver_id != receiver_id:
            return GovernedExecutorResolution.reject("RECEIVER_BINDING_MISMATCH")

        # Step 3: Check expiry at use time (synchronous, no background timer)
        if self._is_binding_expired(handle):
            # Synchronous cleanup via authoritative controller lifecycle API
            # Controller owns both ledger and registry removal
            self._controller.remove_expired_binding(
                receiver_id,
                expected_enablement_id=handle.enablement_id,
                expected_binding_id=handle.binding_id,
            )
            return GovernedExecutorResolution.reject("BINDING_EXPIRED")

        # Step 4: Resolve executor from registry
        executor = self._registry.resolve(receiver_id)
        if executor is None:
            return GovernedExecutorResolution.reject("EXECUTOR_NOT_REGISTERED")

        # Step 5: Verify executor identity matches binding
        if executor.executor_id != handle.executor_identity:
            return GovernedExecutorResolution.reject("EXECUTOR_IDENTITY_MISMATCH")

        return GovernedExecutorResolution.success(executor, handle)

    def _is_binding_expired(self, handle: ProductionExecutorBindingHandle) -> bool:
        """Check if a binding handle is expired using the injected clock.

        Exact boundary: now == expires_at -> expired
        """
        now_str = self._clock.now_iso()
        try:
            now_dt = parse_iso_timestamp(now_str)
            expires_dt = parse_iso_timestamp(handle.expires_at)
        except ValueError:
            return True  # Fail closed on parse error

        # Exact boundary: now >= expires_at means expired
        return expires_dt <= now_dt


# --------------------------------------------------------------------------- #
# Integration contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e22_integration_contract_id() -> str:
    """Compute the deterministic EA-4E.22 integration contract ID."""
    canonical = {
        "schema_id": INTEGRATION_SCHEMA_ID,
        "schema_version": INTEGRATION_SCHEMA_VERSION,
        "artifact_version": INTEGRATION_ARTIFACT_VERSION,
        "ea4e14_execution_contract_id": compute_ea4e14_execution_contract_id(),
        "ea4e17_issuance_contract_id": compute_ea4e17_issuance_contract_id(),
        "ea4e18_integration_contract_id": compute_ea4e18_integration_contract_id(),
        "ea4e21_binding_contract_id": compute_ea4e21_binding_contract_id(),
        "qualified_receivers": {
            k: {
                "transport_contract_id": v["transport_contract_id"],
                "model_binding_id": v["model_binding_id"],
            }
            for k, v in sorted(QUALIFIED_RECEIVERS.items())
        },
        "explicit_receiver_matching": True,
        "preexisting_binding_required": True,
        "no_auto_bind": True,
        "binding_validity_at_use": True,
        "exact_expiration_boundary": "expired",
        "binding_identity_preservation": True,
        "post_teardown_unbound": True,
        "synchronous_expiration_cleanup": True,
        "expired_bindings_do_not_consume_capacity": True,
        "registry_ledger_consistency": True,
        "no_auto_rebind_after_expiry": True,
        "no_receiver_selection": True,
        "no_retry": True,
        "no_binding_retry": True,
        "no_fallback": True,
        "no_failover": True,
        "default_inert_state": True,
        "fake_qualification_only": True,
    }
    return sha256_payload(canonical)
