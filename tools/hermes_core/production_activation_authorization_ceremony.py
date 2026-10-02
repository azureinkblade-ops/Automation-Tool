"""Non-executing EA-4E.62B activation-authorization ceremony ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    DENIED,
    ProductionActivationAuthorizationIssueResult,
    ProductionActivationAuthorizationIssuer,
    ProductionActivationAuthorizationRequest,
    activation_authorization_from_mapping,
)
from tools.hermes_core.production_activation_authorization_store import (
    ProductionActivationAuthorizationStoreError,
)


CANCELLATION_REVOCATION_REASONS = frozenset(
    {
        "OPERATOR_CANCELLED",
        "SCOPE_WITHDRAWN",
        "BINDING_UNAVAILABLE",
        "CREDENTIAL_READINESS_CHANGED",
        "GOVERNING_COMMIT_REVOKED",
        "STORE_EPOCH_ROTATED",
        "SAFETY_HOLD",
    }
)


@dataclass(frozen=True)
class ProductionOperatorIdentity:
    operator_id: str
    identity_provider: str = "trusted-local-host"
    principal_type: str = "local-operator"


class ProductionOperatorIdentityVerifier:
    """Verify one configured non-secret local operator principal."""

    def __init__(self, identity: ProductionOperatorIdentity) -> None:
        if not identity.operator_id.strip():
            raise ValueError("OPERATOR_IDENTITY_MISSING")
        self.identity = identity

    def verify(self, operator_id: str) -> bool:
        return operator_id == self.identity.operator_id


class ProductionActivationAuthorizationCeremonyAuditOwner:
    """Durably records ceremony facts without issuing or activating authority."""

    def __init__(self, store: Any, clock: Any) -> None:
        self.store = store
        self.clock = clock

    def record(
        self,
        artifact_or_request: Any,
        event_type: str,
        detail_code: str = "",
        *,
        state: str | None = None,
    ) -> None:
        self.store.record_ceremony_event(
            artifact_or_request,
            event_type,
            self.clock.now_iso(),
            detail_code,
            state=state,
        )


class ProductionActivationAuthorizationCeremonyCoordinator:
    """Coordinate explicit issue/cancel/revoke actions without execution."""

    def __init__(
        self,
        *,
        issuer: ProductionActivationAuthorizationIssuer,
        binding_controller: Any,
        operator_identity_verifier: ProductionOperatorIdentityVerifier,
        clock: Any,
        credential_preflight: Any,
    ) -> None:
        self._issuer = issuer
        self._policy = issuer._policy
        self._bindings = binding_controller
        self._operator_verifier = operator_identity_verifier
        self._clock = clock
        self._preflight = credential_preflight
        self._audit = ProductionActivationAuthorizationCeremonyAuditOwner(
            self._policy.store, clock
        )

    def issue(self, value: Mapping[str, Any] | None) -> ProductionActivationAuthorizationIssueResult:
        if not isinstance(value, Mapping):
            return ProductionActivationAuthorizationIssueResult(DENIED, "REQUEST_MISSING")
        receiver_id = value.get("receiver_id")
        if not isinstance(receiver_id, str) or not receiver_id:
            return ProductionActivationAuthorizationIssueResult(DENIED, "MALFORMED_REQUEST")
        binding = self._bindings.get_binding_for_receiver(receiver_id)
        if binding is None:
            return ProductionActivationAuthorizationIssueResult(
                DENIED, "EXECUTOR_BINDING_ID_MISSING"
            )
        if getattr(binding, "receiver_id", receiver_id) != receiver_id:
            return ProductionActivationAuthorizationIssueResult(
                DENIED, "EXECUTOR_BINDING_ID_MISMATCH"
            )
        store_id, store_epoch = self._policy.store.lineage()
        request_values = dict(value)
        request_values.pop("operator_id", None)
        request_values.pop("ceremony_id", None)
        request_values.pop("activation_store_id", None)
        request_values.pop("activation_store_epoch", None)
        request_values.pop("executor_binding_id", None)
        request_values.pop("capability_scope", None)
        request_values.update(
            ceremony_id=f"activation-ceremony-{uuid4()}",
            operator_id=self._operator_verifier.identity.operator_id,
            activation_store_id=store_id,
            activation_store_epoch=store_epoch,
            executor_binding_id=binding.binding_id,
            capability_scope=(ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,),
        )
        try:
            request = ProductionActivationAuthorizationRequest(**request_values)
            if not self._operator_verifier.verify(request.operator_id):
                return ProductionActivationAuthorizationIssueResult(
                    DENIED, "OPERATOR_IDENTITY_UNVERIFIED"
                )
            self._policy.store.begin_ceremony(request, self._clock.now_iso())
            self._audit.record(request, "OPERATOR_IDENTITY_VERIFIED")
            self._audit.record(request, "STORE_LINEAGE_VERIFIED")
            if self._preflight is None:
                return self._deny_started(
                    request, "CREDENTIAL_PREFLIGHT_UNAVAILABLE"
                )
            try:
                preflight = self._preflight.check(
                    self._preflight.config_for(
                        receiver_id,
                        transport_contract_id=request.transport_contract_id,
                        model_binding_id=request.model_binding_id,
                    )
                )
            except Exception:
                return self._deny_started(
                    request, "CREDENTIAL_PREFLIGHT_UNAVAILABLE"
                )
            if not preflight.ready:
                return self._deny_started(
                    request,
                    f"CREDENTIAL_PREFLIGHT_DENIED:{preflight.failure_code}",
                )
            self._audit.record(request, "CEREMONY_PREFLIGHT_PASSED")
            self._audit.record(request, "CEREMONY_BINDING_RESERVED", state="BINDING_RESERVED")
            result = self._issuer.issue(request)
            if result.decision != "AUTHORIZED":
                self._release_binding(request)
                self._audit.record(request, "BINDING_RELEASED")
                self._audit.record(request, "CEREMONY_FAILED", result.reason, state="FAILED")
            return result
        except (KeyError, TypeError, ValueError):
            return ProductionActivationAuthorizationIssueResult(DENIED, "MALFORMED_REQUEST")
        except ProductionActivationAuthorizationStoreError as exc:
            return ProductionActivationAuthorizationIssueResult(DENIED, exc.reason)

    def _deny_started(
        self,
        request: ProductionActivationAuthorizationRequest,
        reason: str,
    ) -> ProductionActivationAuthorizationIssueResult:
        self._policy.store.record_denied(request, self._clock.now_iso(), reason)
        self._release_binding(request)
        self._audit.record(request, "BINDING_RELEASED")
        self._audit.record(request, "CEREMONY_FAILED", reason, state="FAILED")
        return ProductionActivationAuthorizationIssueResult(DENIED, reason)

    def cancel(self, authorization: Mapping[str, Any], operator_id: str, reason: str) -> str:
        artifact = self._validated_terminal_request(authorization, operator_id, reason)
        if self._policy.recovery_blocked and (
            self._policy.recovery_blocked()
            if callable(self._policy.recovery_blocked)
            else self._policy.recovery_blocked
        ):
            raise ProductionActivationAuthorizationStoreError("RECOVERY_BLOCKED")
        if self._policy.store.state(artifact.activation_authorization_id) == "ISSUED":
            self._require_exact_binding(artifact)
        state = self._policy.store.cancel(
            artifact.activation_authorization_id, self._clock.now_iso(), reason
        )
        self._release_binding(artifact)
        self._audit.record(artifact, "BINDING_RELEASED")
        self._audit.record(artifact, "CEREMONY_CANCELLED", state="CANCELLED")
        return state

    def revoke(self, authorization: Mapping[str, Any], operator_id: str, reason: str) -> str:
        artifact = self._validated_terminal_request(authorization, operator_id, reason)
        if self._policy.recovery_blocked and (
            self._policy.recovery_blocked()
            if callable(self._policy.recovery_blocked)
            else self._policy.recovery_blocked
        ):
            raise ProductionActivationAuthorizationStoreError("RECOVERY_BLOCKED")
        if self._policy.store.state(artifact.activation_authorization_id) == "CLAIMED":
            self._require_exact_binding(artifact)
        state = self._policy.store.revoke(
            artifact.activation_authorization_id, self._clock.now_iso(), reason
        )
        self._release_binding(artifact)
        self._audit.record(artifact, "BINDING_RELEASED")
        self._audit.record(artifact, "CEREMONY_REVOKED", state="REVOKED")
        return state

    def complete(self, artifact: Any, *, success: bool) -> None:
        stored = self._policy.store.load_artifact(
            artifact.activation_authorization_id
        )
        if stored != artifact.to_dict() or not artifact.verify_hash():
            raise ProductionActivationAuthorizationStoreError("MALFORMED_REQUEST")
        if success and self._policy.store.state(
            artifact.activation_authorization_id
        ) != "CONSUMED":
            raise ProductionActivationAuthorizationStoreError(
                "CEREMONY_STATE_MISMATCH"
            )
        self._audit.record(artifact, "BINDING_RELEASED")
        self._audit.record(
            artifact,
            "CEREMONY_COMPLETED" if success else "CEREMONY_FAILED",
            state="COMPLETED" if success else "FAILED",
        )

    def _release_binding(self, artifact: Any) -> None:
        binding = self._bindings.get_binding_for_receiver(artifact.receiver_id)
        if binding is None:
            return
        if binding.binding_id != artifact.executor_binding_id:
            raise ProductionActivationAuthorizationStoreError(
                "EXECUTOR_BINDING_ID_MISMATCH"
            )
        if not self._bindings.teardown(binding):
            raise ProductionActivationAuthorizationStoreError(
                "CEREMONY_BINDING_RELEASE_FAILED"
            )

    def _require_exact_binding(self, artifact: Any) -> None:
        binding = self._bindings.get_binding_for_receiver(artifact.receiver_id)
        if binding is None:
            raise ProductionActivationAuthorizationStoreError(
                "EXECUTOR_BINDING_NOT_RESERVED"
            )
        if binding.binding_id != artifact.executor_binding_id:
            raise ProductionActivationAuthorizationStoreError(
                "EXECUTOR_BINDING_ID_MISMATCH"
            )

    def _validated_terminal_request(
        self,
        authorization: Mapping[str, Any],
        operator_id: str,
        reason: str,
    ) -> Any:
        artifact = activation_authorization_from_mapping(authorization)
        if artifact is None or not self._operator_verifier.verify(operator_id):
            raise ProductionActivationAuthorizationStoreError("OPERATOR_IDENTITY_MISMATCH")
        if artifact.operator_id != operator_id:
            raise ProductionActivationAuthorizationStoreError("OPERATOR_IDENTITY_MISMATCH")
        if reason not in CANCELLATION_REVOCATION_REASONS:
            raise ProductionActivationAuthorizationStoreError(
                "CANCELLATION_REVOCATION_REASON_INVALID"
            )
        stored = self._policy.store.load_artifact(artifact.activation_authorization_id)
        if stored != artifact.to_dict() or not artifact.verify_hash():
            raise ProductionActivationAuthorizationStoreError("MALFORMED_REQUEST")
        return artifact
