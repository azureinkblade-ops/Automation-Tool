"""EA-4E.44 non-live app-facing execution-authority collaborator.

APPLICATION ACTION != AUTHORITY ISSUER.

Wraps the qualified ProductionIssuancePolicy.evaluate path.
Does not select receivers, bind executors, issue invocation auth,
start receivers, or initialize durable store.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_issuance import (
    ProductionIssuancePolicy,
    ProductionIssuanceRequest,
    ProductionIssuanceResult,
)
from tools.hermes_core.production_wiring import classify_receiver
from tools.hermes_core.receiver_router import RoutingResult


class ProductionAppAuthorityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ProductionAppAuthorityRequest:
    execution_request_id: str | None
    receiver_id: str | None
    transport_contract_id: str | None
    model_binding_id: str | None
    router_contract_id: str | None
    delegation_class: str | None
    requested_operation: str | None
    requested_execution_scope: str | None
    requested_attempt_limit: int | None
    requested_authority_ttl_seconds: int | None
    request_nonce: str | None
    routing_result: RoutingResult | None


@dataclass(frozen=True)
class ProductionAppAuthorityResult:
    authority_decision: str
    authority_reason: str
    issuance_result: ProductionIssuanceResult | None = None
    constructed_request_id: str | None = None
    constructed_receiver_id: str | None = None
    constructed_transport_id: str | None = None
    constructed_model_binding_id: str | None = None
    constructed_scope: str | None = None
    constructed_nonce: str | None = None


class ProductionAppAuthorityCollaborator:
    """Stateless except for the injected issuance-policy dependency."""

    def __init__(self, issuer: ProductionIssuancePolicy | None) -> None:
        self._issuer = issuer

    def issue(self, request: ProductionAppAuthorityRequest | None) -> ProductionAppAuthorityResult:
        if self._issuer is None:
            return self._deny("MISSING_ISSUER_DEPENDENCY")
        if request is None:
            return self._deny("MISSING_REQUEST")
        if not request.execution_request_id or not str(request.execution_request_id).strip():
            return self._deny("MISSING_EXECUTION_REQUEST_ID")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if not request.transport_contract_id or not str(request.transport_contract_id).strip():
            return self._deny("MISSING_TRANSPORT_ID")
        if not request.model_binding_id or not str(request.model_binding_id).strip():
            return self._deny("MISSING_MODEL_BINDING_ID")
        if not request.router_contract_id or not str(request.router_contract_id).strip():
            return self._deny("MISSING_ROUTER_CONTRACT_ID")
        if request.delegation_class is None or not str(request.delegation_class).strip():
            return self._deny("INVALID_DELEGATION_CLASS")
        if request.requested_execution_scope is None or not str(
            request.requested_execution_scope
        ).strip():
            return self._deny("INVALID_SCOPE")
        if not request.request_nonce or not str(request.request_nonce).strip():
            return self._deny("MISSING_NONCE")
        if request.requested_authority_ttl_seconds is None or request.requested_authority_ttl_seconds <= 0:
            return self._deny("INVALID_EXPIRY")
        if request.requested_operation is None or not str(request.requested_operation).strip():
            return self._deny("MISSING_OPERATION")
        if request.requested_attempt_limit is None:
            return self._deny("MISSING_ATTEMPT_LIMIT")
        if request.routing_result is None:
            return self._deny("MISSING_ROUTING_RESULT")

        issuance_request = ProductionIssuanceRequest(
            request_id=request.execution_request_id,
            receiver_id=request.receiver_id,
            routing_result=request.routing_result,
            router_contract_id=request.router_contract_id,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            delegation_class=request.delegation_class,
            requested_operation=request.requested_operation,
            requested_execution_scope=request.requested_execution_scope,
            requested_attempt_limit=request.requested_attempt_limit,
            requested_authority_ttl_seconds=request.requested_authority_ttl_seconds,
            request_nonce=request.request_nonce,
        )
        try:
            issuance_result = self._issuer.evaluate(issuance_request)
        except Exception as exc:
            return ProductionAppAuthorityResult(
                authority_decision="DENY",
                authority_reason=f"ISSUER_EXCEPTION:{type(exc).__name__}",
                constructed_request_id=issuance_request.request_id,
                constructed_receiver_id=issuance_request.receiver_id,
                constructed_transport_id=issuance_request.transport_contract_id,
                constructed_model_binding_id=issuance_request.model_binding_id,
                constructed_scope=issuance_request.requested_execution_scope,
                constructed_nonce=issuance_request.request_nonce,
            )
        decision = "ISSUED" if issuance_result.policy_decision == "ELIGIBLE" else "DENY"
        return ProductionAppAuthorityResult(
            authority_decision=decision,
            authority_reason=issuance_result.policy_reason,
            issuance_result=issuance_result,
            constructed_request_id=issuance_request.request_id,
            constructed_receiver_id=issuance_request.receiver_id,
            constructed_transport_id=issuance_request.transport_contract_id,
            constructed_model_binding_id=issuance_request.model_binding_id,
            constructed_scope=issuance_request.requested_execution_scope,
            constructed_nonce=issuance_request.request_nonce,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppAuthorityResult:
        return ProductionAppAuthorityResult(
            authority_decision="DENY",
            authority_reason=reason,
        )
