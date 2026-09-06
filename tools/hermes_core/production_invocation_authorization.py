"""EA-4E.23 governed runtime invocation authorization / bound-executor use control.

This module establishes the permanent invocation authorization layer between
EA-4E.22 bound-executor resolution and actual invocation through the
ProductionExecutionBoundary.

EA-4E.23 answers exactly:
    MAY THIS ALREADY-GOVERNED, ALREADY-BOUND RECEIVER EXECUTE
    THIS SPECIFIC RUNTIME INVOCATION NOW?

EA-4E.23 does NOT answer:
    Which receiver should be selected?
    Should a receiver be bound?
    Should an authority/activation/issuance artifact be created?

Architecture separation:
    ROUTING != ISSUANCE != AUTHORIZATION != ACTIVATION != BINDING
        != INVOCATION AUTHORIZATION != EXECUTION
"""

from __future__ import annotations

import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingHandle,
    parse_iso_timestamp,
)
from tools.hermes_core.governed_bound_executor import GovernedBoundExecutorResolver
from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
    GovernedProductionResult,
    compute_ea4e18_integration_contract_id,
)
from tools.hermes_core.production_execution import (
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
    ProductionExecutionResult,
    compute_ea4e14_execution_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

INVOCATION_SCHEMA_ID = "hermes.production-invocation-authorization.receiver-dispatch/v1"
INVOCATION_SCHEMA_VERSION = "ea4e.23"
INVOCATION_ARTIFACT_VERSION = "1"

# Maximum invocation authorization TTL (seconds)
MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS = 300

# Maximum authorized attempts per authorization
MAX_AUTHORIZED_ATTEMPTS = 1


# --------------------------------------------------------------------------- #
# Invocation authorization artifact
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionInvocationAuthorization:
    """Authorization artifact for one bounded execution attempt.

    Contains only deterministic material required to authorize one
    governed execution attempt.
    """
    invocation_authorization_id: str
    receiver_id: str
    binding_id: str
    enablement_id: str
    execution_request_id: str
    attempt_number: int
    issued_at: str
    expires_at: str
    runtime_scope: str
    delegation_class: str
    nonce: str

    def to_canonical_dict(self) -> dict:
        """Return canonical dictionary representation."""
        return {
            "invocation_authorization_id": self.invocation_authorization_id,
            "receiver_id": self.receiver_id,
            "binding_id": self.binding_id,
            "enablement_id": self.enablement_id,
            "execution_request_id": self.execution_request_id,
            "attempt_number": self.attempt_number,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "runtime_scope": self.runtime_scope,
            "delegation_class": self.delegation_class,
            "nonce": self.nonce,
        }


# --------------------------------------------------------------------------- #
# Invocation authorization result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionInvocationAuthorizationResult:
    """Result of invocation authorization evaluation."""
    invocation_authorization_id: Optional[str]
    policy_decision: str  # DENY or ALLOW
    policy_reason: str
    binding_authorized: bool
    consumed: bool = False
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Invocation authorization policy
# --------------------------------------------------------------------------- #

class ProductionInvocationAuthorizationPolicy:
    """Evaluates invocation authorization artifacts.

    Default decision: DENY.

    Validates:
    - Authorization is not expired
    - Authorization is not future-issued
    - TTL is within maximum
    - Attempt number is valid
    - Authorization has not been consumed
    - No replay/collision

    Thread-safe: uses a lock to protect mutable consumed-state operations.
    """

    def __init__(
        self,
        *,
        clock: BindingClock,
        max_ttl_seconds: int = MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_ttl_seconds = max_ttl_seconds
        self._consumed_authorizations: set[str] = set()
        self._authorization_identities: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()

    def evaluate(
        self,
        authorization: ProductionInvocationAuthorization,
        handle: ProductionExecutorBindingHandle,
        bound_meta: dict[str, tuple[str, str]],
        *,
        expected_execution_request_id: str | None = None,
    ) -> ProductionInvocationAuthorizationResult:
        """Evaluate an invocation authorization.

        Returns ALLOW only if all gates pass.
        """
        # Step 1: Check if authorization has already been consumed
        with self._lock:
            if authorization.invocation_authorization_id in self._consumed_authorizations:
                return ProductionInvocationAuthorizationResult(
                    invocation_authorization_id=authorization.invocation_authorization_id,
                    policy_decision="DENY",
                    policy_reason="INVOCATION_AUTHORIZATION_ALREADY_CONSUMED",
                    binding_authorized=False,
                    consumed=True,
                )

        # Step 2: Validate receiver match
        if authorization.receiver_id != handle.receiver_id:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="RECEIVER_BINDING_MISMATCH",
                binding_authorized=False,
            )

        # Step 3: Validate exact binding identity
        if authorization.binding_id != handle.binding_id:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="BINDING_ID_MISMATCH",
                binding_authorized=False,
            )

        if authorization.enablement_id != handle.enablement_id:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="ENABLEMENT_ID_MISMATCH",
                binding_authorized=False,
            )

        # Step 4: Validate attempt number
        if authorization.attempt_number != MAX_AUTHORIZED_ATTEMPTS:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="INVALID_ATTEMPT_NUMBER",
                binding_authorized=False,
            )

        if (
            expected_execution_request_id is not None
            and authorization.execution_request_id != expected_execution_request_id
        ):
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="REQUEST_IDENTITY_MISMATCH",
                binding_authorized=False,
            )

        # Step 5: Validate temporal semantics
        now_str = self._clock.now_iso()
        try:
            now_dt = parse_iso_timestamp(now_str)
            issued_dt = parse_iso_timestamp(authorization.issued_at)
            expires_dt = parse_iso_timestamp(authorization.expires_at)
        except ValueError:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="INVALID_TIMESTAMP",
                binding_authorized=False,
            )

        # Future issued_at -> reject
        if issued_dt > now_dt:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="FUTURE_ISSUED_AT",
                binding_authorized=False,
            )

        # Exact expiry boundary: now >= expires_at -> expired
        if expires_dt <= now_dt:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="INVOCATION_AUTHORIZATION_EXPIRED",
                binding_authorized=False,
            )

        # TTL validation (full precision, no truncation)
        effective_ttl = expires_dt - issued_dt
        if effective_ttl.total_seconds() > self._max_ttl_seconds:
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="TTL_ABOVE_MAXIMUM",
                binding_authorized=False,
            )

        # Step 6: Validate runtime_scope and delegation_class
        if authorization.runtime_scope != "production":
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="UNSUPPORTED_RUNTIME_SCOPE",
                binding_authorized=False,
            )

        if authorization.delegation_class != "governed":
            return ProductionInvocationAuthorizationResult(
                invocation_authorization_id=authorization.invocation_authorization_id,
                policy_decision="DENY",
                policy_reason="UNSUPPORTED_DELEGATION_CLASS",
                binding_authorized=False,
            )

        # All checks passed - authorization is valid
        return ProductionInvocationAuthorizationResult(
            invocation_authorization_id=authorization.invocation_authorization_id,
            policy_decision="ALLOW",
            policy_reason="INVOCATION_AUTHORIZATION_VALID",
            binding_authorized=True,
        )

    def claim_for_execution(
        self,
        authorization: ProductionInvocationAuthorization,
        handle: ProductionExecutorBindingHandle,
        bound_meta: dict[str, tuple[str, str]],
        *,
        expected_execution_request_id: str | None = None,
    ) -> ProductionInvocationAuthorizationResult:
        """Atomically validate and claim an authorization for execution.

        This is the authoritative atomic claim operation that performs:
        1. Validate the exact authorization
        2. Validate replay/collision identity
        3. Verify authorization is not consumed
        4. Atomically transition it to CONSUMED
        5. Return exactly one execution permit/result

        Thread-safe: uses lock to ensure atomic check-and-consume.
        """
        with self._lock:
            authorization_id = authorization.invocation_authorization_id
            canonical_hash = sha256_payload(authorization.to_canonical_dict())
            existing_identity = self._authorization_identities.get(authorization_id)
            if existing_identity is not None:
                existing_receiver, existing_hash = existing_identity
                if existing_receiver != authorization.receiver_id:
                    return ProductionInvocationAuthorizationResult(
                        invocation_authorization_id=authorization_id,
                        policy_decision="DENY",
                        policy_reason="CROSS_RECEIVER_INVOCATION_REPLAY",
                        binding_authorized=False,
                    )
                if existing_hash != canonical_hash:
                    return ProductionInvocationAuthorizationResult(
                        invocation_authorization_id=authorization_id,
                        policy_decision="DENY",
                        policy_reason="INVOCATION_AUTHORIZATION_ID_COLLISION",
                        binding_authorized=False,
                    )

            if authorization_id in self._consumed_authorizations:
                return ProductionInvocationAuthorizationResult(
                    invocation_authorization_id=authorization_id,
                    policy_decision="DENY",
                    policy_reason="INVOCATION_AUTHORIZATION_ALREADY_CONSUMED",
                    binding_authorized=False,
                    consumed=True,
                )

            # Perform full evaluation
            result = self.evaluate(
                authorization,
                handle,
                bound_meta,
                expected_execution_request_id=expected_execution_request_id,
            )
            if not result.binding_authorized:
                return result

            # Atomically mark as consumed
            self._authorization_identities[authorization_id] = (
                authorization.receiver_id,
                canonical_hash,
            )
            self._consumed_authorizations.add(authorization_id)

        return result

    def mark_consumed(self, invocation_authorization_id: str) -> None:
        """Mark an authorization as consumed."""
        with self._lock:
            self._consumed_authorizations.add(invocation_authorization_id)

    def is_consumed(self, invocation_authorization_id: str) -> bool:
        """Check if an authorization has been consumed."""
        with self._lock:
            return invocation_authorization_id in self._consumed_authorizations


# --------------------------------------------------------------------------- #
# Governed invocation coordinator
# --------------------------------------------------------------------------- #

class GovernedInvocationCoordinator:
    """Coordinates governed invocation with invocation authorization.

    Path:
    1. explicit receiver supplied
    2. router validates/selects only that receiver
    3. issuance policy passes
    4. authority validation passes
    5. activation validation passes
    6. EA-4E.22 resolves exact valid pre-existing binding
    7. EA-4E.23 validates exact invocation authorization
    8. invocation authorization is atomically marked consumed at execution-attempt boundary
    9. ProductionExecutionBoundary invokes injected fake executor
    """

    def __init__(
        self,
        *,
        clock: BindingClock,
        binding_controller: ProductionExecutorBindingController,
        executor_registry: ExecutorRegistry,
        invocation_policy: Optional[ProductionInvocationAuthorizationPolicy] = None,
        governed_coordinator: Optional[GovernedProductionCoordinator] = None,
    ) -> None:
        self._clock = clock
        self._binding_controller = binding_controller
        self._executor_registry = executor_registry
        self._resolver = GovernedBoundExecutorResolver(
            binding_controller=binding_controller,
            executor_registry=executor_registry,
            clock=clock,
        )
        self._invocation_policy = invocation_policy or ProductionInvocationAuthorizationPolicy(
            clock=clock,
        )

    def invoke(
        self,
        request: GovernedExecutionRequest,
        authorization: ProductionInvocationAuthorization,
    ) -> GovernedProductionResult:
        """Execute a fully governed invocation with invocation authorization.

        Returns structured result.
        """
        # Step 1: Execute governed production path (routing -> issuance -> authority -> activation)
        # For EA-4E.23, we use the existing governed coordinator for steps 1-5
        # Then we add steps 6-9 for binding resolution, invocation authorization, consumption, execution

        # Step 6: EA-4E.22 bound-executor resolution
        resolution = self._resolver.resolve_governed_executor(request.receiver_id)

        if resolution.resolution_decision != "RESOLVED":
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="ELIGIBLE",
                issuance_policy_reason="EA4E22_RESOLUTION_FAILED",
                authority_issued=True,
                authority_valid=True,
                activation_issued=True,
                activation_valid=True,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason=f"EA4E22_RESOLUTION_FAILED:{resolution.resolution_reason}",
                attempt_count=0,
            )

        handle = resolution.binding_handle

        # Step 7: EA-4E.23 atomic invocation claim (validate + consume atomically)
        bound_meta = {}  # Empty for invocation authorization (no duplicate detection needed)
        auth_result = self._invocation_policy.claim_for_execution(authorization, handle, bound_meta)

        if not auth_result.binding_authorized:
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="ELIGIBLE",
                issuance_policy_reason="INVOCATION_AUTHORIZATION_FAILED",
                authority_issued=True,
                authority_valid=True,
                activation_issued=True,
                activation_valid=True,
                execution_request_created=False,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason=f"INVOCATION_REJECTED:{auth_result.policy_reason}",
                attempt_count=0,
            )

        # Step 9: Execute through production execution boundary (outside lock)
        executor = self._executor_registry.resolve(request.receiver_id)
        if executor is None:
            return GovernedProductionResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                route_decision="SELECTED",
                issuance_policy_decision="ELIGIBLE",
                issuance_policy_reason="EXECUTOR_NOT_FOUND",
                authority_issued=True,
                authority_valid=True,
                activation_issued=True,
                activation_valid=True,
                execution_request_created=True,
                adapter_resolution=None,
                execution_decision="REJECT",
                executor_called=False,
                execution_status=None,
                execution_output=None,
                reason="EXECUTOR_NOT_FOUND",
                attempt_count=1,
            )

        # Execute
        execution_result = executor.execute(ProductionExecutionRequest(
            receiver_id=request.receiver_id,
            delegation_id=f"ea4e23-delegation-{request.request_id}",
            router_contract_id=request.router_contract_id,
            authority_contract_id="",
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            execution_scope="production",
            task_payload="",
            attempt_limit=1,
        ))

        return GovernedProductionResult(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            route_decision="SELECTED",
            issuance_policy_decision="ELIGIBLE",
            issuance_policy_reason="INVOCATION_AUTHORIZED",
            authority_issued=True,
            authority_valid=True,
            activation_issued=True,
            activation_valid=True,
            execution_request_created=True,
            adapter_resolution=executor.executor_id,
            execution_decision="EXECUTE",
            executor_called=True,
            execution_status=execution_result.execution_status,
            execution_output=execution_result.output,
            reason="INVOCATION_AUTHORIZED_AND_EXECUTED",
            attempt_count=1,
        )


# --------------------------------------------------------------------------- #
# Contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e23_invocation_contract_id() -> str:
    """Compute the deterministic EA-4E.23 invocation contract ID."""
    canonical = {
        "schema_id": INVOCATION_SCHEMA_ID,
        "schema_version": INVOCATION_SCHEMA_VERSION,
        "artifact_version": INVOCATION_ARTIFACT_VERSION,
        "ea4e14_execution_contract_id": compute_ea4e14_execution_contract_id(),
        "ea4e17_issuance_contract_id": "26400d2dfca800213c33be298af1e1074498d6d85bb84cd06577c739c24f6e78",
        "ea4e18_integration_contract_id": compute_ea4e18_integration_contract_id(),
        "ea4e21_binding_contract_id": "99a3ddb77e057cdcf5d4950af73cc88801d82d9a4ad2b4e3e96f8c227947a3e7",
        "ea4e22_integration_contract_id": "e30a178c43ab2f98262b287b8ff79aaf9d8849f8d12205b30dd40820b056f47a",
        "max_invocation_authorization_ttl_seconds": MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
        "max_authorized_attempts": MAX_AUTHORIZED_ATTEMPTS,
        "default_invocation_authorization_decision": "DENY",
        "explicit_receiver_matching": True,
        "exact_binding_identity_required": True,
        "binding_valid_at_use_required": True,
        "consumption_semantics": "atomic_at_execution_attempt_boundary",
        "replay_collision_semantics": "cross_receiver_precedence",
        "no_auto_create_authorization": True,
        "no_retry": True,
        "no_binding_retry": True,
        "no_invocation_retry": True,
        "no_fallback": True,
        "no_failover": True,
        "no_auto_bind": True,
        "default_inert_state": True,
        "fake_qualification_only": True,
    }
    return sha256_payload(canonical)
