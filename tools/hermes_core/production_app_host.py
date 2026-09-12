"""Fail-closed host adapter for the governed production application action.

The host reconstructs externally supplied artifacts and delegates to the
qualified ``ProductionAppUserAction``. It never issues authority, activates
production, binds an executor, bootstraps a store, or selects a receiver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from tools.hermes_core.production_activation import ProductionActivation
from tools.hermes_core.production_app_user_action import (
    ProductionAppUserAction,
    ProductionAppUserActionRequest,
    ProductionAppUserActionResult,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.receiver_dispatch import DispatchAuthority, DispatchAuthorityScope


ALLOWED_OPERATION = "receiver-dispatch"
ALLOWED_RUNTIME_SCOPE = "production"


@dataclass(frozen=True)
class ProductionAppHostResult:
    decision: str
    reason: str
    request_id: str = ""
    receiver_id: str = ""
    runtime_scope: str = ""
    execution_decision: str = "NOT_EVALUATED"
    execution_status: str | None = None
    execution_output: str | None = None
    executor_called: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.decision == "ALLOW",
            "decision": self.decision,
            "reason": self.reason,
            "requestId": self.request_id,
            "receiverId": self.receiver_id,
            "runtimeScope": self.runtime_scope,
            "execution": {
                "decision": self.execution_decision,
                "status": self.execution_status,
                "output": self.execution_output,
                "executorCalled": self.executor_called,
            },
        }


class ProductionAppHostAction:
    """Translate one explicit host request into the qualified user action."""

    def __init__(self, user_action: ProductionAppUserAction | None) -> None:
        self._user_action = user_action

    def submit(self, payload: Mapping[str, Any] | None) -> ProductionAppHostResult:
        if self._user_action is None:
            return self._deny("MISSING_GOVERNED_ACTION_DEPENDENCY")
        if not isinstance(payload, Mapping):
            return self._deny("INVALID_HOST_REQUEST")
        if payload.get("operation") != ALLOWED_OPERATION:
            return self._deny("INVALID_OPERATION")
        if payload.get("runtime_scope") != ALLOWED_RUNTIME_SCOPE:
            return self._deny("INVALID_RUNTIME_SCOPE")
        if type(payload.get("production_activation_explicit")) is not bool:
            return self._deny("INVALID_ACTIVATION_INTENT")

        try:
            request = ProductionAppUserActionRequest(
                request_id=_optional_string(payload.get("request_id")),
                receiver_id=_optional_receiver(payload.get("receiver_id")),
                task_payload=_optional_string_or_none(payload.get("task_payload")),
                production_activation_explicit=payload["production_activation_explicit"],
                runtime_scope=payload["runtime_scope"],
                authorization_issue_request=_issue_request(
                    payload.get("authorization_issue_request")
                ),
                transport_contract_id=_optional_string_or_none(
                    payload.get("transport_contract_id")
                ),
                model_binding_id=_optional_string_or_none(payload.get("model_binding_id")),
                execution_authority=_execution_authority(
                    payload.get("execution_authority")
                ),
                activation=_activation(payload.get("activation")),
            )
        except (KeyError, TypeError, ValueError):
            return self._deny("INVALID_GOVERNANCE_ARTIFACT")

        try:
            result = self._user_action.submit(request)
        except Exception as exc:
            return self._deny(f"GOVERNED_ACTION_EXCEPTION:{type(exc).__name__}")
        return _public_result(result)

    @staticmethod
    def _deny(reason: str) -> ProductionAppHostResult:
        return ProductionAppHostResult(decision="DENY", reason=reason)


def _optional_string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_receiver(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("expected string")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("expected mapping")
    return value


def _issue_request(value: object) -> ProductionInvocationAuthorizationIssueRequest | None:
    if value is None:
        return None
    item = _mapping(value)
    return ProductionInvocationAuthorizationIssueRequest(
        issue_request_id=item["issue_request_id"],
        execution_request_id=item["execution_request_id"],
        receiver_id=item["receiver_id"],
        binding_id=item["binding_id"],
        enablement_id=item["enablement_id"],
        nonce=item["nonce"],
        requested_ttl_seconds=item["requested_ttl_seconds"],
        attempt_number=item["attempt_number"],
        runtime_scope=item["runtime_scope"],
        delegation_class=item["delegation_class"],
    )


def _execution_authority(value: object) -> DispatchAuthority | None:
    if value is None:
        return None
    item = _mapping(value)
    scope = _mapping(item["scope"])
    return DispatchAuthority(
        authority_id=item["authority_id"],
        artifact_version=item["artifact_version"],
        artifact_hash=item["artifact_hash"],
        receiver_id=item["receiver_id"],
        transport_contract_id=item["transport_contract_id"],
        model_binding_id=item["model_binding_id"],
        router_contract_id=item["router_contract_id"],
        scope=DispatchAuthorityScope(
            operation=scope["operation"],
            receiver_id=scope["receiver_id"],
            attempt_limit=scope["attempt_limit"],
        ),
        delegation_class=item["delegation_class"],
        decision=item["decision"],
        issued_at=item["issued_at"],
        expires_at=item["expires_at"],
        nonce=item["nonce"],
    )


def _activation(value: object) -> ProductionActivation | None:
    if value is None:
        return None
    item = _mapping(value)
    return ProductionActivation(
        activation_id=item["activation_id"],
        artifact_version=item["artifact_version"],
        artifact_hash=item["artifact_hash"],
        receiver_id=item["receiver_id"],
        router_contract_id=item["router_contract_id"],
        authority_contract_id=item["authority_contract_id"],
        transport_contract_id=item["transport_contract_id"],
        model_binding_id=item["model_binding_id"],
        activation_mode=item["activation_mode"],
        execution_scope=item["execution_scope"],
        delegation_class=item["delegation_class"],
    )


def _public_result(result: ProductionAppUserActionResult) -> ProductionAppHostResult:
    runtime_result = None
    callsite = result.callsite_result
    if callsite is not None and callsite.adapter_result is not None:
        caller = callsite.adapter_result.caller_result
        if caller is not None and caller.entrypoint_result is not None:
            governed = caller.entrypoint_result.caller_result
            if governed is not None:
                runtime_result = governed.runtime_result

    return ProductionAppHostResult(
        decision=result.user_action_decision,
        reason=result.user_action_reason,
        request_id=result.constructed_request_id or "",
        receiver_id=result.constructed_receiver_id or "",
        runtime_scope=result.constructed_runtime_scope or "",
        execution_decision=(
            runtime_result.execution_decision if runtime_result is not None else "NOT_EVALUATED"
        ),
        execution_status=(runtime_result.execution_status if runtime_result is not None else None),
        execution_output=(runtime_result.execution_output if runtime_result is not None else None),
        executor_called=(runtime_result.executor_called if runtime_result is not None else False),
    )
