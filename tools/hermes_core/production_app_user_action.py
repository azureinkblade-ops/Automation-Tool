"""EA-4E.41 non-live explicit user-action handler.

USER ACTION != APP CALL-SITE.

Manual/operator request translator to ProductionAppCallSite.invoke.
Disconnected from app.py. Cannot enable the outer feature gate or master enable.
No authority, binding, invocation-auth, store, retry, fallback, or Grok.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_app_callsite import (
    ProductionAppCallSite,
    ProductionAppCallSiteRequest,
    ProductionAppCallSiteResult,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_wiring import classify_receiver


ALLOWED_RUNTIME_SCOPES = frozenset({"production"})


@dataclass(frozen=True)
class ProductionAppUserActionRequest:
    request_id: str
    receiver_id: str | None
    task_payload: str | None = None
    production_activation_explicit: bool = False
    runtime_scope: str = "production"
    authorization_issue_request: ProductionInvocationAuthorizationIssueRequest | None = None
    transport_contract_id: str | None = None
    model_binding_id: str | None = None


@dataclass
class ProductionAppUserActionResult:
    user_action_decision: str
    user_action_reason: str
    callsite_invoked: bool = False
    callsite_result: ProductionAppCallSiteResult | None = None
    constructed_request_id: str | None = None
    constructed_receiver_id: str | None = None
    constructed_runtime_scope: str | None = None
    constructed_activation_intent: bool | None = None


class ProductionAppUserAction:
    """Explicit manual handler. Stateless. Downstream is ProductionAppCallSite.invoke only."""

    def __init__(self, callsite: ProductionAppCallSite | None) -> None:
        self._callsite = callsite

    def submit(self, request: ProductionAppUserActionRequest) -> ProductionAppUserActionResult:
        if self._callsite is None:
            return self._deny("MISSING_CALLSITE_DEPENDENCY")
        if not request.request_id or not str(request.request_id).strip():
            return self._deny("MISSING_REQUEST_ID")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if request.runtime_scope not in ALLOWED_RUNTIME_SCOPES:
            return self._deny("INVALID_RUNTIME_SCOPE")
        if not request.production_activation_explicit:
            return self._deny("APPLICATION_ACTIVATION_INTENT_FALSE")
        issue = request.authorization_issue_request
        if issue is not None and issue.receiver_id != request.receiver_id:
            return self._deny("USER_ACTION_TO_CALLSITE_RECEIVER_MUTATION")
        if issue is not None and issue.execution_request_id != request.request_id:
            return self._deny("REQUEST_ID_MISMATCH")

        callsite_request = ProductionAppCallSiteRequest(
            request_id=request.request_id,
            receiver_id=request.receiver_id,
            task_payload=request.task_payload,
            production_activation_explicit=request.production_activation_explicit,
            runtime_scope=request.runtime_scope,
            authorization_issue_request=issue,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
        )
        try:
            callsite_result = self._callsite.invoke(callsite_request)
        except Exception as exc:
            return ProductionAppUserActionResult(
                user_action_decision="DENY",
                user_action_reason=f"CALLSITE_EXCEPTION:{type(exc).__name__}",
                callsite_invoked=True,
                constructed_request_id=callsite_request.request_id,
                constructed_receiver_id=callsite_request.receiver_id,
                constructed_runtime_scope=callsite_request.runtime_scope,
                constructed_activation_intent=callsite_request.production_activation_explicit,
            )
        decision = "ALLOW" if callsite_result.callsite_decision == "ALLOW" else "DENY"
        return ProductionAppUserActionResult(
            user_action_decision=decision,
            user_action_reason=callsite_result.callsite_reason,
            callsite_invoked=True,
            callsite_result=callsite_result,
            constructed_request_id=callsite_request.request_id,
            constructed_receiver_id=callsite_request.receiver_id,
            constructed_runtime_scope=callsite_request.runtime_scope,
            constructed_activation_intent=callsite_request.production_activation_explicit,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppUserActionResult:
        return ProductionAppUserActionResult(
            user_action_decision="DENY",
            user_action_reason=reason,
            callsite_invoked=False,
        )
