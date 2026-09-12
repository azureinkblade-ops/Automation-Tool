"""EA-4E.39 non-live real app call-site enablement boundary.

APP CALL-SITE != APP ADAPTER.

Minimal future application seam for invoking ProductionAppAdapter.submit.
app.py is not modified. Outer feature gate defaults to DISABLED and does not
replace master-enable or per-request activation.

No authority, binding, invocation-auth, store, retry, fallback, or Grok.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.hermes_core.production_activation import ProductionActivation
from tools.hermes_core.production_app_adapter import (
    ProductionAppAdapter,
    ProductionAppAdapterRequest,
    ProductionAppAdapterResult,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_wiring import classify_receiver
from tools.hermes_core.receiver_dispatch import DispatchAuthority


ALLOWED_RUNTIME_SCOPES = frozenset({"production"})
REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT = "DISABLED"


@dataclass(frozen=True)
class ProductionAppCallSiteRequest:
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
class ProductionAppCallSiteResult:
    callsite_decision: str
    callsite_reason: str
    adapter_invoked: bool = False
    adapter_result: ProductionAppAdapterResult | None = None
    constructed_request_id: str | None = None
    constructed_receiver_id: str | None = None
    constructed_runtime_scope: str | None = None
    constructed_activation_intent: bool | None = None


class ProductionAppCallSite:
    """Explicit, default-inactive application call-site. Stateless request handling."""

    def __init__(
        self,
        adapter: ProductionAppAdapter | None,
        feature_gate: str = REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT,
    ) -> None:
        self._adapter = adapter
        self._feature_gate = feature_gate

    def invoke(self, request: ProductionAppCallSiteRequest) -> ProductionAppCallSiteResult:
        if self._feature_gate != "ENABLED":
            return self._deny("OUTER_FEATURE_GATE_DISABLED")
        if self._adapter is None:
            return self._deny("MISSING_APP_ADAPTER_DEPENDENCY")
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
            return self._deny("REAL_CALLSITE_TO_ADAPTER_RECEIVER_MUTATION")
        if issue is not None and issue.execution_request_id != request.request_id:
            return self._deny("REQUEST_ID_MISMATCH")

        adapter_request = ProductionAppAdapterRequest(
            request_id=request.request_id,
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
            adapter_result = self._adapter.submit(adapter_request)
        except Exception as exc:
            return ProductionAppCallSiteResult(
                callsite_decision="DENY",
                callsite_reason=f"APP_ADAPTER_EXCEPTION:{type(exc).__name__}",
                adapter_invoked=True,
                constructed_request_id=adapter_request.request_id,
                constructed_receiver_id=adapter_request.receiver_id,
                constructed_runtime_scope=adapter_request.runtime_scope,
                constructed_activation_intent=adapter_request.production_activation_explicit,
            )
        decision = "ALLOW" if adapter_result.adapter_decision == "ALLOW" else "DENY"
        return ProductionAppCallSiteResult(
            callsite_decision=decision,
            callsite_reason=adapter_result.adapter_reason,
            adapter_invoked=True,
            adapter_result=adapter_result,
            constructed_request_id=adapter_request.request_id,
            constructed_receiver_id=adapter_request.receiver_id,
            constructed_runtime_scope=adapter_request.runtime_scope,
            constructed_activation_intent=adapter_request.production_activation_explicit,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppCallSiteResult:
        return ProductionAppCallSiteResult(
            callsite_decision="DENY",
            callsite_reason=reason,
            adapter_invoked=False,
        )
