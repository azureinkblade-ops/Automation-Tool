"""EA-4E.38 non-live app-facing adapter to ProductionApplicationCaller.

APP CALL-SITE != APPLICATION CALLER.

Translates explicit application-layer input into ProductionApplicationRequest
and invokes ProductionApplicationCaller.submit. Defaults remain disabled.
No authority, binding, invocation-auth, store, retry, fallback, or Grok.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_activation import ProductionActivation
from tools.hermes_core.production_application_caller import (
    ProductionApplicationCaller,
    ProductionApplicationRequest,
    ProductionApplicationResult,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_wiring import classify_receiver
from tools.hermes_core.receiver_dispatch import DispatchAuthority


ALLOWED_RUNTIME_SCOPES = frozenset({"production"})


@dataclass(frozen=True)
class ProductionAppAdapterRequest:
    request_id: str
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
class ProductionAppAdapterResult:
    adapter_decision: str
    adapter_reason: str
    caller_invoked: bool = False
    caller_result: ProductionApplicationResult | None = None
    constructed_request_id: str | None = None
    constructed_receiver_id: str | None = None
    constructed_runtime_scope: str | None = None
    constructed_activation_intent: bool | None = None


class ProductionAppAdapter:
    """Stateless app-facing adapter. Downstream is ProductionApplicationCaller.submit only."""

    def __init__(self, caller: ProductionApplicationCaller | None) -> None:
        self._caller = caller

    def submit(self, request: ProductionAppAdapterRequest) -> ProductionAppAdapterResult:
        if self._caller is None:
            return self._deny("MISSING_APPLICATION_CALLER_DEPENDENCY")
        if not request.request_id or not str(request.request_id).strip():
            return self._deny("MISSING_APP_REQUEST_ID")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if request.runtime_scope not in ALLOWED_RUNTIME_SCOPES:
            return self._deny("INVALID_RUNTIME_SCOPE")
        if not request.production_activation_explicit:
            return self._deny("APPLICATION_ACTIVATION_INTENT_FALSE")
        issue = request.authorization_issue_request
        if issue is not None and issue.receiver_id != request.receiver_id:
            return self._deny("APP_TO_CALLER_RECEIVER_MUTATION")
        if issue is not None and issue.execution_request_id != request.request_id:
            return self._deny("REQUEST_ID_MISMATCH")

        app_request = ProductionApplicationRequest(
            application_request_id=request.request_id,
            receiver_id=request.receiver_id,
            task_payload=request.task_payload,
            production_activation_explicit=request.production_activation_explicit,
            runtime_scope=request.runtime_scope,
            authorization_issue_request=issue,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            execution_authority=request.execution_authority,
            activation=request.activation,
        )
        try:
            caller_result = self._caller.submit(app_request)
        except Exception as exc:
            return ProductionAppAdapterResult(
                adapter_decision="DENY",
                adapter_reason=f"APPLICATION_CALLER_EXCEPTION:{type(exc).__name__}",
                caller_invoked=True,
                constructed_request_id=app_request.application_request_id,
                constructed_receiver_id=app_request.receiver_id,
                constructed_runtime_scope=app_request.runtime_scope,
                constructed_activation_intent=app_request.production_activation_explicit,
            )
        decision = "ALLOW" if caller_result.application_decision == "ALLOW" else "DENY"
        return ProductionAppAdapterResult(
            adapter_decision=decision,
            adapter_reason=caller_result.application_reason,
            caller_invoked=True,
            caller_result=caller_result,
            constructed_request_id=app_request.application_request_id,
            constructed_receiver_id=app_request.receiver_id,
            constructed_runtime_scope=app_request.runtime_scope,
            constructed_activation_intent=app_request.production_activation_explicit,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppAdapterResult:
        return ProductionAppAdapterResult(
            adapter_decision="DENY",
            adapter_reason=reason,
            caller_invoked=False,
        )
