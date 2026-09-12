"""EA-4E.46 app-facing invocation-authorization request provisioning.

The provisioner validates explicit parent authority and binding artifacts and
constructs the existing issuer request. It does not issue, persist, claim,
consume, cache, retry, or execute anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ProductionExecutorBindingHandle,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    parse_iso_timestamp,
)
from tools.hermes_core.production_invocation_authorization import (
    MAX_AUTHORIZED_ATTEMPTS,
    MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_issuance import (
    ALLOWED_DELEGATION_CLASS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.production_wiring import classify_receiver
from tools.hermes_core.receiver_dispatch import DispatchAuthority, DispatchAuthorityScope


@dataclass(frozen=True)
class ProductionAppInvocationAuthorizationRequest:
    issue_request_id: str | None
    execution_request_id: str | None
    receiver_id: str | None
    execution_authority: DispatchAuthority | None
    binding_handle: ProductionExecutorBindingHandle | None
    transport_contract_id: str | None
    model_binding_id: str | None
    runtime_scope: str | None
    requested_operation: str | None
    requested_ttl_seconds: int | None
    attempt_number: int | None
    nonce: str | None
    delegation_class: str | None


@dataclass(frozen=True)
class ProductionAppInvocationAuthorizationResult:
    provisioning_decision: str
    provisioning_reason: str
    issue_request: ProductionInvocationAuthorizationIssueRequest | None = None
    execution_authority_id: str | None = None
    binding_id: str | None = None
    enablement_id: str | None = None
    receiver_id: str | None = None
    transport_contract_id: str | None = None
    model_binding_id: str | None = None
    runtime_scope: str | None = None
    requested_operation: str | None = None
    nonce: str | None = None


class ProductionAppInvocationAuthorizationProvisioner:
    """Stateless validator and mapper for the external issuer boundary."""

    def __init__(self, clock: BindingClock | None) -> None:
        self._clock = clock

    def provision(
        self,
        request: ProductionAppInvocationAuthorizationRequest | None,
    ) -> ProductionAppInvocationAuthorizationResult:
        if self._clock is None:
            return self._deny("MISSING_CLOCK_DEPENDENCY")
        if request is None:
            return self._deny("MISSING_REQUEST")
        if not isinstance(request, ProductionAppInvocationAuthorizationRequest):
            return self._deny("MALFORMED_REQUEST")

        required_ids = {
            "issue_request_id": request.issue_request_id,
            "execution_request_id": request.execution_request_id,
            "transport_contract_id": request.transport_contract_id,
            "model_binding_id": request.model_binding_id,
            "runtime_scope": request.runtime_scope,
            "requested_operation": request.requested_operation,
            "nonce": request.nonce,
            "delegation_class": request.delegation_class,
        }
        for field_name, value in required_ids.items():
            if not isinstance(value, str) or not value.strip():
                return self._deny(f"MISSING_{field_name.upper()}")

        receiver_denial = classify_receiver(request.receiver_id)
        if receiver_denial is not None:
            return self._deny(receiver_denial)
        if request.execution_authority is None:
            return self._deny("MISSING_EXECUTION_AUTHORITY")
        if request.binding_handle is None:
            return self._deny("MISSING_BINDING_HANDLE")
        if not isinstance(request.execution_authority, DispatchAuthority):
            return self._deny("MALFORMED_EXECUTION_AUTHORITY")
        if not isinstance(request.execution_authority.scope, DispatchAuthorityScope):
            return self._deny("MALFORMED_EXECUTION_AUTHORITY_SCOPE")
        if not isinstance(request.binding_handle, ProductionExecutorBindingHandle):
            return self._deny("MALFORMED_BINDING_HANDLE")
        if request.requested_ttl_seconds is None:
            return self._deny("MISSING_REQUESTED_TTL_SECONDS")
        if request.attempt_number is None:
            return self._deny("MISSING_ATTEMPT_NUMBER")
        if type(request.requested_ttl_seconds) is not int:
            return self._deny("INVALID_AUTHORIZATION_TTL")
        if type(request.attempt_number) is not int:
            return self._deny("INVALID_ATTEMPT_NUMBER")

        authority = request.execution_authority
        binding = request.binding_handle
        qualified = QUALIFIED_RECEIVERS[request.receiver_id]
        qualified_executor = QUALIFIED_EXECUTOR_IMPLEMENTATIONS.get(request.receiver_id, {})

        if authority.decision != "GRANTED":
            return self._deny("EXECUTION_AUTHORITY_NOT_GRANTED")
        if not authority.verify_hash():
            return self._deny("EXECUTION_AUTHORITY_HASH_INVALID")
        if authority.receiver_id != request.receiver_id or authority.scope.receiver_id != request.receiver_id:
            return self._deny("RECEIVER_AUTHORITY_MISMATCH")
        if binding.receiver_id != request.receiver_id:
            return self._deny("RECEIVER_BINDING_MISMATCH")
        if binding.executor_identity != qualified_executor.get("executor_identity"):
            return self._deny("BINDING_EXECUTOR_IDENTITY_MISMATCH")
        if request.transport_contract_id != qualified["transport_contract_id"]:
            return self._deny("TRANSPORT_CONTRACT_MISMATCH")
        if authority.transport_contract_id != request.transport_contract_id:
            return self._deny("AUTHORITY_TRANSPORT_MISMATCH")
        if request.model_binding_id != qualified["model_binding_id"]:
            return self._deny("MODEL_BINDING_MISMATCH")
        if authority.model_binding_id != request.model_binding_id:
            return self._deny("AUTHORITY_MODEL_BINDING_MISMATCH")
        if authority.scope.operation != request.requested_operation:
            return self._deny("OPERATION_SCOPE_MISMATCH")
        if request.runtime_scope != "production":
            return self._deny("UNSUPPORTED_RUNTIME_SCOPE")
        if request.delegation_class != ALLOWED_DELEGATION_CLASS:
            return self._deny("UNSUPPORTED_DELEGATION_CLASS")
        if authority.delegation_class != request.delegation_class:
            return self._deny("AUTHORITY_DELEGATION_CLASS_MISMATCH")
        if request.attempt_number != MAX_AUTHORIZED_ATTEMPTS:
            return self._deny("INVALID_ATTEMPT_NUMBER")
        if authority.scope.attempt_limit != request.attempt_number:
            return self._deny("ATTEMPT_SCOPE_MISMATCH")
        if not 1 <= request.requested_ttl_seconds <= MAX_INVOCATION_AUTHORIZATION_TTL_SECONDS:
            return self._deny("INVALID_AUTHORIZATION_TTL")

        try:
            now = parse_iso_timestamp(self._clock.now_iso())
            authority_expiry = parse_iso_timestamp(authority.expires_at)
            binding_expiry = parse_iso_timestamp(binding.expires_at)
        except (TypeError, ValueError):
            return self._deny("INVALID_TIMESTAMP")
        if authority_expiry <= now:
            return self._deny("EXECUTION_AUTHORITY_EXPIRED")
        if binding_expiry <= now:
            return self._deny("BINDING_EXPIRED")
        requested_expiry = now + timedelta(seconds=request.requested_ttl_seconds)
        if requested_expiry > authority_expiry:
            return self._deny("AUTHORIZATION_OUTLIVES_EXECUTION_AUTHORITY")
        if requested_expiry > binding_expiry:
            return self._deny("AUTHORIZATION_OUTLIVES_BINDING")

        issue_request = ProductionInvocationAuthorizationIssueRequest(
            issue_request_id=request.issue_request_id,
            execution_request_id=request.execution_request_id,
            receiver_id=request.receiver_id,
            binding_id=binding.binding_id,
            enablement_id=binding.enablement_id,
            nonce=request.nonce,
            requested_ttl_seconds=request.requested_ttl_seconds,
            attempt_number=request.attempt_number,
            runtime_scope=request.runtime_scope,
            delegation_class=request.delegation_class,
        )
        return ProductionAppInvocationAuthorizationResult(
            provisioning_decision="PROVISIONED",
            provisioning_reason="EXPLICIT_ISSUE_REQUEST_PROVISIONED",
            issue_request=issue_request,
            execution_authority_id=authority.authority_id,
            binding_id=binding.binding_id,
            enablement_id=binding.enablement_id,
            receiver_id=request.receiver_id,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            runtime_scope=request.runtime_scope,
            requested_operation=request.requested_operation,
            nonce=request.nonce,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppInvocationAuthorizationResult:
        return ProductionAppInvocationAuthorizationResult(
            provisioning_decision="DENY",
            provisioning_reason=reason,
        )
