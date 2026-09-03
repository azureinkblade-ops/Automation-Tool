"""EA-4E.7 execution-authority integration boundary.

This module establishes the deterministic, fail-closed interface between:

1. receiver selection (EA-4E.6 router); and
2. execution authorization.

The router may identify a qualified receiver. It must NOT itself create
permission to execute that receiver. EA-4E.7 proves that execution can
proceed only when a separate, explicit execution-authority artifact
satisfies the frozen authority contract.

This is a fake/non-live qualification: no real receiver process is started.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


# --------------------------------------------------------------------------- #
# Authority schema version
# --------------------------------------------------------------------------- #

AUTHORITY_SCHEMA_ID = "hermes.execution-authority.receiver-dispatch/v1"
AUTHORITY_SCHEMA_VERSION = "ea4e.7"
AUTHORITY_ARTIFACT_VERSION = "1"


# --------------------------------------------------------------------------- #
# Authority scope
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DispatchAuthorityScope:
    """Least-authority scope for receiver dispatch."""
    operation: str
    receiver_id: str
    attempt_limit: int = 1

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "receiver_id": self.receiver_id,
            "attempt_limit": self.attempt_limit,
        }


# --------------------------------------------------------------------------- #
# Authority artifact
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DispatchAuthority:
    """Execution-authority artifact for receiver dispatch.

    Binds the receiver selection to a specific execution permission.
    Created ONLY by explicit authority issuance, never by the router.
    """
    authority_id: str
    artifact_version: str
    artifact_hash: str
    receiver_id: str
    transport_contract_id: str
    model_binding_id: str
    router_contract_id: str
    scope: DispatchAuthorityScope
    delegation_class: str
    decision: str  # "GRANTED" or "DENIED"
    issued_at: str
    expires_at: str
    nonce: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "artifact_version": self.artifact_version,
            "receiver_id": self.receiver_id,
            "transport_contract_id": self.transport_contract_id,
            "model_binding_id": self.model_binding_id,
            "router_contract_id": self.router_contract_id,
            "scope": self.scope.to_canonical_dict(),
            "delegation_class": self.delegation_class,
            "decision": self.decision,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())

    def verify_hash(self) -> bool:
        return sha256_payload(self.to_canonical_dict()) == self.artifact_hash


# --------------------------------------------------------------------------- #
# Dispatch decision
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DispatchDecision:
    """Result of the execution-authority validation + fake dispatch.

    ``process_started`` is ALWAYS False for fake qualification.
    ``dispatch_started`` is ALWAYS False for fake qualification.
    """
    receiver_id: Optional[str]
    route_decision: str
    authority_valid: bool
    dispatch_decision: str
    reason: str
    process_started: bool = False
    model_invoked: bool = False
    dispatch_started: bool = False


# --------------------------------------------------------------------------- #
# Authority builder
# --------------------------------------------------------------------------- #

def _derive_authority_id(preimage: dict[str, Any]) -> str:
    return "dispatch-authority-" + sha256_payload(preimage)[:16]


def build_dispatch_authority(
    *,
    receiver_id: str,
    transport_contract_id: str,
    model_binding_id: str,
    router_contract_id: str,
    scope: DispatchAuthorityScope,
    delegation_class: str,
    decision: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> DispatchAuthority:
    """Build a dispatch-authority artifact.

    This is the ONLY way to create execution authority for dispatch.
    The router never calls this function.
    """
    if decision not in ("GRANTED", "DENIED"):
        raise ValueError(f"Invalid decision: {decision}")

    preimage = {
        "artifact_version": AUTHORITY_ARTIFACT_VERSION,
        "receiver_id": receiver_id,
        "transport_contract_id": transport_contract_id,
        "model_binding_id": model_binding_id,
        "router_contract_id": router_contract_id,
        "scope": scope.to_canonical_dict(),
        "delegation_class": delegation_class,
        "decision": decision,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
    }
    authority_id = _derive_authority_id(preimage)
    full = {**preimage, "authority_id": authority_id}
    artifact_hash = sha256_payload(full)
    return DispatchAuthority(
        authority_id=authority_id,
        artifact_version=AUTHORITY_ARTIFACT_VERSION,
        artifact_hash=artifact_hash,
        receiver_id=receiver_id,
        transport_contract_id=transport_contract_id,
        model_binding_id=model_binding_id,
        router_contract_id=router_contract_id,
        scope=scope,
        delegation_class=delegation_class,
        decision=decision,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=nonce,
    )


# --------------------------------------------------------------------------- #
# Execution-authority validator
# --------------------------------------------------------------------------- #

class ExecutionAuthorityValidator:
    """Validates dispatch-authority artifacts against frozen contracts.

    Fail-closed: any mismatch rejects dispatch.
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
        authority: Optional[DispatchAuthority],
        route_result: RoutingResult,
    ) -> DispatchDecision:
        """Validate authority and produce a dispatch decision.

        NEVER starts a process. NEVER invokes a model.
        """
        # 1. Route must have selected a receiver
        if route_result.route_decision != "SELECTED":
            return DispatchDecision(
                receiver_id=None,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="ROUTE_NOT_SELECTED",
            )

        # 2. Authority must be present
        if authority is None:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="EXECUTION_AUTHORITY_MISSING",
            )

        # 3. Authority must be GRANTED
        if authority.decision != "GRANTED":
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="EXECUTION_AUTHORITY_DENIED",
            )

        # 4. Authority receiver must match routed receiver
        if authority.receiver_id != route_result.receiver_id:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="AUTHORITY_RECEIVER_MISMATCH",
            )

        # 5. Router contract must match
        if authority.router_contract_id != self._router_contract_id:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="ROUTER_CONTRACT_MISMATCH",
            )

        # 6. Transport contract must match frozen value
        expected_transport = self._qualified.get(authority.receiver_id, {}).get(
            "transport_contract_id", ""
        )
        if authority.transport_contract_id != expected_transport:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="TRANSPORT_CONTRACT_MISMATCH",
            )

        # 7. Model binding must match frozen value
        expected_model = self._qualified.get(authority.receiver_id, {}).get(
            "model_binding_id", ""
        )
        if authority.model_binding_id != expected_model:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="MODEL_BINDING_MISMATCH",
            )

        # 8. Authority hash must verify
        if not authority.verify_hash():
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="MALFORMED_AUTHORITY",
            )

        # 9. Authority must not be expired
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(authority.expires_at.replace("Z", "+00:00"))
        if now >= expires:
            return DispatchDecision(
                receiver_id=route_result.receiver_id,
                route_decision=route_result.route_decision,
                authority_valid=False,
                dispatch_decision="REJECT",
                reason="AUTHORITY_EXPIRED",
            )

        # All checks passed: authorize dispatch (but do NOT start process)
        return DispatchDecision(
            receiver_id=route_result.receiver_id,
            route_decision=route_result.route_decision,
            authority_valid=True,
            dispatch_decision="AUTHORIZED",
            reason="AUTHORITY_VALID",
        )


# --------------------------------------------------------------------------- #
# Fake dispatch layer
# --------------------------------------------------------------------------- #

class FakeDispatchLayer:
    """Records dispatch decisions without executing any receiver.

    This is the boundary between authorization and execution.
    It NEVER starts a process or invokes a model.
    """

    def __init__(self, *, router: Optional[ReceiverRouter] = None) -> None:
        self._router = router or get_default_router()
        self._validator = ExecutionAuthorityValidator(
            router_contract_id=compute_ea4e6_router_contract_id(),
        )

    def dispatch(
        self,
        *,
        receiver_id: str,
        authority: Optional[DispatchAuthority],
        delegation_class: str = "governed",
    ) -> DispatchDecision:
        """Route, validate authority, and produce a dispatch decision.

        NEVER starts a process. NEVER invokes a model.
        """
        # Step 1: Route selection
        route_result = self._router.route(RoutingRequest(
            receiver_id=receiver_id,
            execution_authority_present=authority is not None,
        ))

        # Step 2: Authority validation (fail-closed)
        return self._validator.validate(authority, route_result)


# --------------------------------------------------------------------------- #
# Canonical authority material
# --------------------------------------------------------------------------- #

def get_authority_canonical_material() -> dict[str, Any]:
    """Return deterministic canonical material for EA-4E.7 authority contract."""
    return {
        "schema_id": AUTHORITY_SCHEMA_ID,
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "artifact_version": AUTHORITY_ARTIFACT_VERSION,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "qualified_receivers": {
            k: QUALIFIED_RECEIVERS[k] for k in sorted(QUALIFIED_RECEIVERS)
        },
        "authority_scope": {
            "operation": "receiver-dispatch",
            "attempt_limit": 1,
        },
        "fail_closed_reasons": [
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
            "router_starts_receiver": False,
            "authority_validation_starts_receiver": False,
            "fake_dispatch_starts_receiver": False,
        },
    }


def compute_ea4e7_authority_contract_id() -> str:
    """Compute the canonical EA-4E.7 authority contract ID."""
    return sha256_payload(get_authority_canonical_material())
