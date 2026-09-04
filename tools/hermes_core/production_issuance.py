"""EA-4E.17 governed production authority / activation issuance policy.

This module establishes the permanent reusable control-plane policy that
determines whether an already explicitly selected receiver is eligible
to receive:
  1. a bounded DispatchAuthority; and
  2. a bounded ProductionActivation.

The policy does NOT select a receiver.
The policy does NOT execute a receiver.
The policy does NOT invoke a model.
The policy does NOT create persistent production enablement.
The policy does NOT infer intent from task text.
The policy does NOT infer receiver choice from environment state.
The policy does NOT fall back or fail over between receivers.

Target control-plane flow:
    Explicit Receiver Selection
    → RoutingResult
    → ProductionIssuanceRequest
    → ProductionIssuancePolicy
    → bounded DispatchAuthority OR rejection
    → bounded ProductionActivation OR rejection
    → ProductionIssuanceResult
    → NO EXECUTION

Future execution remains separate:
    ProductionIssuanceResult
    → separately governed ProductionExecutionBoundary
    → receiver execution
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from tools.hermes_core.hashing import canonical_json, sha256_payload
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingResult,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    DispatchAuthorityScope,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    build_production_activation,
    compute_ea4e11_activation_contract_id,
)
from tools.hermes_core.production_execution import (
    compute_ea4e14_execution_contract_id,
)


# --------------------------------------------------------------------------- #
# Issuance schema
# --------------------------------------------------------------------------- #

ISSUANCE_SCHEMA_ID = "hermes.production-issuance.receiver-dispatch/v1"
ISSUANCE_SCHEMA_VERSION = "ea4e.17"
ISSUANCE_ARTIFACT_VERSION = "1"

# Policy constants
ALLOWED_OPERATION = "receiver-dispatch"
ALLOWED_EXECUTION_SCOPE = "production"
ALLOWED_DELEGATION_CLASS = "governed"
MAX_ISSUABLE_ATTEMPT_LIMIT = 1
MAX_AUTHORITY_TTL_SECONDS = 3600  # 1 hour
DEFAULT_ISSUANCE_DECISION = "DENY"


# --------------------------------------------------------------------------- #
# Issuance request
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionIssuanceRequest:
    """Structured request for production authority/activation issuance.

    The receiver must already be explicitly selected upstream.
    This request does NOT select a receiver.
    """
    request_id: str
    receiver_id: str
    routing_result: RoutingResult
    router_contract_id: str
    transport_contract_id: str
    model_binding_id: str
    delegation_class: str
    requested_operation: str
    requested_execution_scope: str
    requested_attempt_limit: int
    requested_authority_ttl_seconds: int
    request_nonce: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "receiver_id": self.receiver_id,
            "routing_result": {
                "receiver_id": self.routing_result.receiver_id,
                "route_decision": self.routing_result.route_decision,
                "route_reason": self.routing_result.route_reason,
            },
            "router_contract_id": self.router_contract_id,
            "transport_contract_id": self.transport_contract_id,
            "model_binding_id": self.model_binding_id,
            "delegation_class": self.delegation_class,
            "requested_operation": self.requested_operation,
            "requested_execution_scope": self.requested_execution_scope,
            "requested_attempt_limit": self.requested_attempt_limit,
            "requested_authority_ttl_seconds": self.requested_authority_ttl_seconds,
            "request_nonce": self.request_nonce,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())


# --------------------------------------------------------------------------- #
# Issuance result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ProductionIssuanceResult:
    """Structured result of production issuance policy evaluation.

    Does NOT contain secrets, tokens, or credentials.
    """
    request_id: str
    receiver_id: str
    policy_decision: str  # ELIGIBLE or REJECT
    policy_reason: str
    authority_issued: bool
    authority_id: Optional[str]
    authority_valid: Optional[bool]
    activation_issued: bool
    activation_id: Optional[str]
    activation_valid: Optional[bool]
    attempt_limit: int
    execution_scope: str
    authority: Optional[DispatchAuthority]
    activation: Optional[ProductionActivation]


# --------------------------------------------------------------------------- #
# Clock collaborator for deterministic time
# --------------------------------------------------------------------------- #

class ClockCollaborator:
    """Injected clock for deterministic authority expiry computation."""

    def __init__(self, *, now: str) -> None:
        self._now = now

    def now_iso(self) -> str:
        return self._now

    def now_plus_seconds(self, seconds: int) -> str:
        """Compute expiry time from injected now."""
        from datetime import datetime, timedelta, timezone
        base = datetime.fromisoformat(self._now)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        expiry = base + timedelta(seconds=seconds)
        return expiry.isoformat()


# --------------------------------------------------------------------------- #
# Issuance policy
# --------------------------------------------------------------------------- #

class ProductionIssuancePolicy:
    """Pure/deterministic policy for production authority/activation issuance.

    Does NOT execute receivers.
    Does NOT select receivers.
    Does NOT call models.
    """

    def __init__(
        self,
        *,
        clock: ClockCollaborator,
        qualified_receivers: Optional[dict[str, dict[str, str]]] = None,
        max_attempt_limit: int = MAX_ISSUABLE_ATTEMPT_LIMIT,
        max_authority_ttl: int = MAX_AUTHORITY_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._qualified = qualified_receivers or QUALIFIED_RECEIVERS
        self._max_attempt_limit = max_attempt_limit
        self._max_authority_ttl = max_authority_ttl

    def evaluate(
        self,
        request: ProductionIssuanceRequest,
    ) -> ProductionIssuanceResult:
        """Evaluate issuance request against policy.

        Default decision is DENY. Only explicit eligibility passes.
        """
        # Gate 1: Receiver must be present
        if not request.receiver_id:
            return self._reject(request, "MISSING_RECEIVER")

        # Gate 2: Receiver must be in qualified set
        if request.receiver_id not in self._qualified:
            return self._reject(request, "UNSUPPORTED_RECEIVER")

        # Gate 3: Route result must show SELECTED
        if request.routing_result.route_decision != "SELECTED":
            return self._reject(request, "ROUTE_NOT_SELECTED")

        # Gate 4: Route receiver must match request receiver
        if request.routing_result.receiver_id != request.receiver_id:
            return self._reject(request, "ROUTING_RECEIVER_MISMATCH")

        # Gate 5: Router contract must match
        expected_router_contract = compute_ea4e6_router_contract_id()
        if request.router_contract_id != expected_router_contract:
            return self._reject(request, "ROUTER_CONTRACT_MISMATCH")

        # Gate 6: Transport contract must match receiver binding
        receiver_bindings = self._qualified[request.receiver_id]
        if request.transport_contract_id != receiver_bindings["transport_contract_id"]:
            return self._reject(request, "TRANSPORT_CONTRACT_MISMATCH")

        # Gate 7: Model binding must match receiver binding
        if request.model_binding_id != receiver_bindings["model_binding_id"]:
            return self._reject(request, "MODEL_BINDING_MISMATCH")

        # Gate 8: Delegation class must be allowed
        if request.delegation_class != ALLOWED_DELEGATION_CLASS:
            return self._reject(request, "DELEGATION_CLASS_MISMATCH")

        # Gate 9: Operation must be allowed
        if request.requested_operation != ALLOWED_OPERATION:
            return self._reject(request, "OPERATION_MISMATCH")

        # Gate 10: Execution scope must be allowed
        if request.requested_execution_scope != ALLOWED_EXECUTION_SCOPE:
            return self._reject(request, "EXECUTION_SCOPE_MISMATCH")

        # Gate 11: Attempt limit must be exactly 1
        if request.requested_attempt_limit < 1:
            return self._reject(request, "ATTEMPT_LIMIT_ZERO")
        if request.requested_attempt_limit > self._max_attempt_limit:
            return self._reject(request, "ATTEMPT_LIMIT_ABOVE_MAX")

        # Gate 12: TTL must be positive and within max
        if request.requested_authority_ttl_seconds <= 0:
            return self._reject(request, "INVALID_TTL")
        if request.requested_authority_ttl_seconds > self._max_authority_ttl:
            return self._reject(request, "TTL_ABOVE_MAX")

        # All gates pass — issue authority then activation
        return self._issue(request)

    def _reject(
        self,
        request: ProductionIssuanceRequest,
        reason: str,
    ) -> ProductionIssuanceResult:
        return ProductionIssuanceResult(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            policy_decision="REJECT",
            policy_reason=reason,
            authority_issued=False,
            authority_id=None,
            authority_valid=None,
            activation_issued=False,
            activation_id=None,
            activation_valid=None,
            attempt_limit=request.requested_attempt_limit,
            execution_scope=request.requested_execution_scope,
            authority=None,
            activation=None,
        )

    def _issue(
        self,
        request: ProductionIssuanceRequest,
    ) -> ProductionIssuanceResult:
        """Issue authority then activation after all policy gates pass."""
        now = self._clock.now_iso()
        expires = self._clock.now_plus_seconds(request.requested_authority_ttl_seconds)

        try:
            authority = build_dispatch_authority(
                receiver_id=request.receiver_id,
                transport_contract_id=request.transport_contract_id,
                model_binding_id=request.model_binding_id,
                router_contract_id=request.router_contract_id,
                scope=DispatchAuthorityScope(
                    operation=request.requested_operation,
                    receiver_id=request.receiver_id,
                    attempt_limit=request.requested_attempt_limit,
                ),
                delegation_class=request.delegation_class,
                decision="GRANTED",
                issued_at=now,
                expires_at=expires,
                nonce=request.request_nonce,
            )
        except Exception as e:
            return ProductionIssuanceResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                policy_decision="REJECT",
                policy_reason=f"AUTHORITY_BUILDER_FAILURE:{type(e).__name__}",
                authority_issued=False,
                authority_id=None,
                authority_valid=None,
                activation_issued=False,
                activation_id=None,
                activation_valid=None,
                attempt_limit=request.requested_attempt_limit,
                execution_scope=request.requested_execution_scope,
                authority=None,
                activation=None,
            )

        # Validate the issued authority
        authority_valid = authority.verify_hash()
        if not authority_valid:
            return ProductionIssuanceResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                policy_decision="REJECT",
                policy_reason="AUTHORITY_VALIDATOR_REJECTION",
                authority_issued=True,
                authority_id=authority.authority_id,
                authority_valid=False,
                activation_issued=False,
                activation_id=None,
                activation_valid=None,
                attempt_limit=request.requested_attempt_limit,
                execution_scope=request.requested_execution_scope,
                authority=authority,
                activation=None,
            )

        # Issue activation only after authority is valid
        try:
            activation = build_production_activation(
                receiver_id=request.receiver_id,
                router_contract_id=request.router_contract_id,
                authority_contract_id=compute_ea4e7_authority_contract_id(),
                transport_contract_id=request.transport_contract_id,
                model_binding_id=request.model_binding_id,
                activation_mode="ENABLED",
                execution_scope=request.requested_execution_scope,
                delegation_class=request.delegation_class,
            )
        except Exception as e:
            return ProductionIssuanceResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                policy_decision="REJECT",
                policy_reason=f"ACTIVATION_BUILDER_FAILURE:{type(e).__name__}",
                authority_issued=True,
                authority_id=authority.authority_id,
                authority_valid=True,
                activation_issued=False,
                activation_id=None,
                activation_valid=None,
                attempt_limit=request.requested_attempt_limit,
                execution_scope=request.requested_execution_scope,
                authority=authority,
                activation=None,
            )

        # Validate activation
        activation_valid = activation.verify_hash()
        if not activation_valid:
            return ProductionIssuanceResult(
                request_id=request.request_id,
                receiver_id=request.receiver_id,
                policy_decision="REJECT",
                policy_reason="ACTIVATION_VALIDATOR_REJECTION",
                authority_issued=True,
                authority_id=authority.authority_id,
                authority_valid=True,
                activation_issued=True,
                activation_id=activation.activation_id,
                activation_valid=False,
                attempt_limit=request.requested_attempt_limit,
                execution_scope=request.requested_execution_scope,
                authority=authority,
                activation=activation,
            )

        return ProductionIssuanceResult(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            policy_decision="ELIGIBLE",
            policy_reason="POLICY_ELIGIBLE",
            authority_issued=True,
            authority_id=authority.authority_id,
            authority_valid=True,
            activation_issued=True,
            activation_id=activation.activation_id,
            activation_valid=True,
            attempt_limit=request.requested_attempt_limit,
            execution_scope=request.requested_execution_scope,
            authority=authority,
            activation=activation,
        )


# --------------------------------------------------------------------------- #
# Issuance contract computation
# --------------------------------------------------------------------------- #

def compute_ea4e17_issuance_contract_id() -> str:
    """Compute the deterministic EA-4E.17 issuance contract ID."""
    canonical = {
        "schema_id": ISSUANCE_SCHEMA_ID,
        "schema_version": ISSUANCE_SCHEMA_VERSION,
        "qualified_receivers": {
            k: {
                "transport_contract_id": v["transport_contract_id"],
                "model_binding_id": v["model_binding_id"],
            }
            for k, v in sorted(QUALIFIED_RECEIVERS.items())
        },
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "authority_contract_id": compute_ea4e7_authority_contract_id(),
        "activation_contract_id": compute_ea4e11_activation_contract_id(),
        "execution_contract_id": compute_ea4e14_execution_contract_id(),
        "allowed_operation": ALLOWED_OPERATION,
        "allowed_execution_scope": ALLOWED_EXECUTION_SCOPE,
        "allowed_delegation_class": ALLOWED_DELEGATION_CLASS,
        "max_attempt_limit": MAX_ISSUABLE_ATTEMPT_LIMIT,
        "max_authority_ttl": MAX_AUTHORITY_TTL_SECONDS,
        "default_issuance_decision": DEFAULT_ISSUANCE_DECISION,
    }
    return sha256_payload(canonical)
