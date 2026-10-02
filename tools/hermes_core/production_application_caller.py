"""EA-4E.37 non-live application caller to ProductionEntryPoint.

APPLICATION CALLER != AUTHORITY ISSUER != EXECUTOR.

Stateless conversion of an explicit application request into an EA-4E.36
entry-point request. Defaults remain disabled. No authority, binding,
invocation-auth issuance, store initialization, retry, fallback, or Grok.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_activation import ProductionActivation
from tools.hermes_core.production_entrypoint import (
    ProductionEntryPoint,
    ProductionEntryPointRequest,
    ProductionEntryPointResult,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_wiring import classify_receiver
from tools.hermes_core.receiver_dispatch import DispatchAuthority


ALLOWED_RUNTIME_SCOPES = frozenset({"production"})


@dataclass(frozen=True)
class ProductionApplicationRequest:
    application_request_id: str
    receiver_id: str | None
    task_payload: str | None = None
    production_activation_explicit: bool = False
    runtime_scope: str = "production"
    authorization_issue_request: ProductionInvocationAuthorizationIssueRequest | None = None
    transport_contract_id: str | None = None
    model_binding_id: str | None = None
    execution_authority: DispatchAuthority | None = None
    activation: ProductionActivation | None = None


@dataclass
class ProductionApplicationResult:
    application_decision: str
    application_reason: str
    entrypoint_called: bool = False
    entrypoint_result: ProductionEntryPointResult | None = None
    constructed_request_id: str | None = None
    constructed_receiver_id: str | None = None
    constructed_runtime_scope: str | None = None


class ProductionApplicationCaller:
    """Immutable/stateless application caller. No cached request state."""

    def __init__(self, entrypoint: ProductionEntryPoint | None) -> None:
        self._entrypoint = entrypoint

    def submit(self, request: ProductionApplicationRequest) -> ProductionApplicationResult:
        if self._entrypoint is None:
            return self._deny("MISSING_ENTRYPOINT_DEPENDENCY")
        if not request.application_request_id or not str(request.application_request_id).strip():
            return self._deny("MISSING_APPLICATION_REQUEST_ID")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if request.runtime_scope not in ALLOWED_RUNTIME_SCOPES:
            return self._deny("INVALID_RUNTIME_SCOPE")
        if self._entrypoint.master_enable != "ENABLED":
            return self._deny("PRODUCTION_MASTER_ENABLE_DISABLED")
        if not request.production_activation_explicit:
            return self._deny("APPLICATION_ACTIVATION_INTENT_FALSE")
        issue = request.authorization_issue_request
        if issue is not None and issue.receiver_id != request.receiver_id:
            return self._deny("CALLER_TO_ENTRYPOINT_RECEIVER_MUTATION")
        if issue is not None and issue.execution_request_id != request.application_request_id:
            return self._deny("REQUEST_ID_MISMATCH")

        entry_request = ProductionEntryPointRequest(
            request_id=request.application_request_id,
            receiver_id=request.receiver_id,
            task_payload=request.task_payload,
            production_activation_explicit=request.production_activation_explicit,
            runtime_scope=request.runtime_scope,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            authorization_issue_request=issue,
            execution_authority=request.execution_authority,
            activation=request.activation,
        )
        try:
            entry_result = self._entrypoint.handle(entry_request)
        except Exception as exc:
            return ProductionApplicationResult(
                application_decision="DENY",
                application_reason=f"ENTRYPOINT_EXCEPTION:{type(exc).__name__}",
                entrypoint_called=True,
                constructed_request_id=entry_request.request_id,
                constructed_receiver_id=entry_request.receiver_id,
                constructed_runtime_scope=entry_request.runtime_scope,
            )
        decision = "ALLOW" if entry_result.entrypoint_decision == "ALLOW" else "DENY"
        return ProductionApplicationResult(
            application_decision=decision,
            application_reason=entry_result.entrypoint_reason,
            entrypoint_called=True,
            entrypoint_result=entry_result,
            constructed_request_id=entry_request.request_id,
            constructed_receiver_id=entry_request.receiver_id,
            constructed_runtime_scope=entry_request.runtime_scope,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionApplicationResult:
        return ProductionApplicationResult(
            application_decision="DENY",
            application_reason=reason,
            entrypoint_called=False,
        )
