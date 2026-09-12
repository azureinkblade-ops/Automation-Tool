"""In-process lifecycle ownership for one governed production request.

The owner requires an existing explicit binding, validates and consumes a
pre-issued activation authorization, delegates once to the qualified host
action, and tears down request activation and that exact binding in ``finally``.
It does not bind, issue authority, issue activation authorization, retry, or
select a fallback receiver.
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Mapping

from tools.hermes_core.production_app_host import (
    ProductionAppHostAction,
    ProductionAppHostResult,
    _activation,
    _execution_authority,
)
from tools.hermes_core.production_app_recovery import (
    SUPPORTED_RECEIVERS,
    ProductionRecoveryStore,
)
from tools.hermes_core.production_executor_binding import (
    ProductionExecutorBindingController,
)
from tools.hermes_core.production_activation_authorization import (
    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
    ProductionActivationAuthorizationPolicy,
    ProductionActivationAuthorizationValidator,
    ProductionAppActivationTransitionOwner,
    activation_authorization_from_mapping,
)
from tools.hermes_core.receiver_router import ReceiverRouter, RoutingRequest


class ProductionRequestAdmissionController:
    """Fail closed when another request owns the single lifecycle slot."""

    def __init__(self) -> None:
        self._state_lock = Lock()
        self._owner_request_id: str | None = None

    def acquire(self, request_id: str) -> bool:
        with self._state_lock:
            if self._owner_request_id is not None:
                return False
            self._owner_request_id = request_id
            return True

    def release(self, request_id: str) -> bool:
        with self._state_lock:
            if self._owner_request_id != request_id:
                return False
            self._owner_request_id = None
            return True

    @property
    def owner_request_id(self) -> str | None:
        with self._state_lock:
            return self._owner_request_id


class ProductionAppRequestLifecycleOwner:
    """Own one already-bound governed request through request-scoped teardown."""

    def __init__(
        self,
        governed_action: ProductionAppHostAction | None,
        binding_controller: ProductionExecutorBindingController | None,
        admission_controller: ProductionRequestAdmissionController | None = None,
        recovery_store: ProductionRecoveryStore | None = None,
        host_instance_id: str | None = None,
        credential_preflight: Any = None,
        activation_authorization_policy: ProductionActivationAuthorizationPolicy | None = None,
        activation_authorization_validator: ProductionActivationAuthorizationValidator | None = None,
        activation_transition_owner: ProductionAppActivationTransitionOwner | None = None,
        authority_validator: Any = None,
        router: ReceiverRouter | None = None,
        activation_feature_gate_state: str = "DISABLED",
        activation_ceremony_coordinator: Any = None,
    ) -> None:
        self._governed_action = governed_action
        self._binding_controller = binding_controller
        self._admission_controller = (
            admission_controller
            if admission_controller is not None
            else ProductionRequestAdmissionController()
        )
        self._recovery_store = recovery_store
        self._host_instance_id = host_instance_id
        self._preflight = credential_preflight
        self._activation_authorization_policy = activation_authorization_policy
        self._activation_authorization_validator = activation_authorization_validator
        self._activation_transition_owner = activation_transition_owner
        self._authority_validator = authority_validator
        self._router = router
        self._activation_feature_gate_state = activation_feature_gate_state
        self._activation_ceremony_coordinator = activation_ceremony_coordinator

    def submit(self, payload: Mapping[str, Any] | None) -> ProductionAppHostResult:
        if self._governed_action is None or self._binding_controller is None:
            return self._deny("MISSING_REQUEST_LIFECYCLE_DEPENDENCY")

        if not isinstance(payload, Mapping):
            return self._governed_action.submit(payload)

        receiver_id = payload.get("receiver_id")
        if not isinstance(receiver_id, str) or not receiver_id.strip():
            return self._governed_action.submit(payload)

        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            return self._deny("MISSING_REQUEST_ID")

        if self._recovery_store is not None and self._recovery_store.has_unresolved():
            return self._deny("PRODUCTION_RECOVERY_REQUIRED")

        if not self._admission_controller.acquire(request_id):
            return self._deny("PRODUCTION_REQUEST_CONCURRENCY_LIMIT")

        try:
            if receiver_id not in SUPPORTED_RECEIVERS:
                return self._deny("UNSUPPORTED_RECEIVER")
            if self._recovery_store is not None:
                if not self._host_instance_id:
                    return self._deny("MISSING_RECOVERY_HOST_IDENTITY")
                self._recovery_store.begin(
                    request_id,
                    receiver_id,
                    self._host_instance_id,
                )
            return self._submit_admitted(payload, receiver_id)
        finally:
            self._admission_controller.release(request_id)

    def activate_only(
        self, payload: Mapping[str, Any] | None
    ) -> ProductionAppHostResult:
        """Complete request-scoped activation without dispatching the action."""
        if not isinstance(payload, Mapping):
            return self._deny("INVALID_ACTIVATION_CEREMONY_REQUEST")
        return self._activate_only(payload)

    def _activate_only(
        self,
        payload: Mapping[str, Any],
    ) -> ProductionAppHostResult:
        if self._governed_action is None or self._binding_controller is None:
            return self._deny("MISSING_REQUEST_LIFECYCLE_DEPENDENCY")

        receiver_id = payload.get("receiver_id")
        if not isinstance(receiver_id, str) or not receiver_id.strip():
            return self._deny("INVALID_ACTIVATION_CEREMONY_REQUEST")

        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            return self._deny("MISSING_REQUEST_ID")

        if self._recovery_store is not None and self._recovery_store.has_unresolved():
            return self._deny("PRODUCTION_RECOVERY_REQUIRED")

        if not self._admission_controller.acquire(request_id):
            return self._deny("PRODUCTION_REQUEST_CONCURRENCY_LIMIT")

        try:
            if receiver_id not in SUPPORTED_RECEIVERS:
                return self._deny("UNSUPPORTED_RECEIVER")
            if self._recovery_store is not None:
                if not self._host_instance_id:
                    return self._deny("MISSING_RECOVERY_HOST_IDENTITY")
                self._recovery_store.begin(
                    request_id,
                    receiver_id,
                    self._host_instance_id,
                )
            return self._submit_admitted(
                payload,
                receiver_id,
                execute_governed_action=False,
            )
        finally:
            self._admission_controller.release(request_id)

    def _submit_admitted(
        self,
        payload: Mapping[str, Any],
        receiver_id: str,
        *,
        execute_governed_action: bool = True,
    ) -> ProductionAppHostResult:
        if self._preflight is not None:
            preflight_result = self._preflight.check(
                self._preflight.config_for(
                    receiver_id,
                    transport_contract_id=payload.get("transport_contract_id"),
                    model_binding_id=payload.get("model_binding_id"),
                )
            )
            if not preflight_result.ready:
                if self._recovery_store is not None:
                    self._recovery_store.mark_clean(payload["request_id"])
                return self._deny(
                    f"CREDENTIAL_PREFLIGHT_DENIED:{preflight_result.failure_code}"
                )

        binding = self._binding_controller.get_binding_for_receiver(receiver_id)
        if binding is None:
            if self._recovery_store is not None:
                self._recovery_store.mark_clean(payload["request_id"])
            return self._deny("MISSING_EXPLICIT_BINDING")

        if self._recovery_store is not None:
            self._recovery_store.transition(
                payload["request_id"],
                "BINDING_OWNED",
                binding_id=binding.binding_id,
                enablement_id=binding.enablement_id,
            )
            issue_request = payload.get("authorization_issue_request")
            if isinstance(issue_request, Mapping):
                issue_request_id = issue_request.get("issue_request_id")
                if isinstance(issue_request_id, str) and issue_request_id:
                    self._recovery_store.transition(
                        payload["request_id"],
                        "INVOCATION_AUTH_PERSISTED",
                        invocation_authorization_id=issue_request_id,
                    )
            self._recovery_store.transition(payload["request_id"], "REQUEST_ENTERED")

        result: ProductionAppHostResult | None = None
        action_error: Exception | None = None
        cleanup_error: str | None = None
        activation_recovery_required = False
        activation_authorization = None
        try:
            activation_dependencies = (
                self._activation_authorization_policy,
                self._activation_authorization_validator,
                self._activation_transition_owner,
                self._authority_validator,
                self._router,
            )
            if any(item is not None for item in activation_dependencies):
                if not all(item is not None for item in activation_dependencies):
                    result = self._deny("MISSING_ACTIVATION_AUTHORIZATION_DEPENDENCY")
                elif self._activation_feature_gate_state != "ENABLED":
                    result = self._deny("OUTER_FEATURE_GATE_DISABLED")
                else:
                    try:
                        authority = _execution_authority(payload.get("execution_authority"))
                        production_activation = _activation(payload.get("activation"))
                        activation_authorization = activation_authorization_from_mapping(
                            payload.get("activation_authorization")
                        )
                    except (KeyError, TypeError, ValueError):
                        result = self._deny("INVALID_GOVERNANCE_ARTIFACT")
                    else:
                        route = self._router.route(RoutingRequest(receiver_id=receiver_id))
                        authority_result = self._authority_validator.validate(authority, route)
                        if not authority_result.authority_valid:
                            result = self._deny(
                                f"EXECUTION_AUTHORITY_INVALID:{authority_result.reason}"
                            )
                        else:
                            claim = self._activation_authorization_policy.claim(
                                activation_authorization,
                                validator=self._activation_authorization_validator,
                                request_id=payload["request_id"],
                                receiver_id=receiver_id,
                                feature_gate_state=self._activation_feature_gate_state,
                                operator_id=(
                                    self._activation_authorization_policy
                                    .operator_identity_verifier.identity.operator_id
                                ),
                                executor_binding_id=binding.binding_id,
                                requested_capabilities=(
                                    ACTIVATION_CAPABILITY_ENTER_REQUEST_SCOPE,
                                ),
                            )
                            if claim.decision != "AUTHORIZED":
                                result = self._deny(
                                    f"ACTIVATION_AUTHORIZATION_DENIED:{claim.reason}"
                                )
                            else:
                                transition = self._activation_transition_owner.transition(
                                    request_id=payload["request_id"],
                                    receiver_id=receiver_id,
                                    claimed_authorization=claim,
                                    production_activation=production_activation,
                                )
                                activation_recovery_required = transition.recovery_required
                                if transition.decision != "AUTHORIZED":
                                    result = self._deny(
                                        f"PRODUCTION_ACTIVATION_DENIED:{transition.reason}"
                                    )
            if result is None:
                if execute_governed_action:
                    result = self._governed_action.submit(payload)
                else:
                    result = ProductionAppHostResult(
                        decision="ALLOW",
                        reason="PRODUCTION_ACTIVATION_CEREMONY_COMPLETED",
                    )
        except Exception as exc:
            action_error = exc
        finally:
            if self._recovery_store is not None:
                self._recovery_store.transition(payload["request_id"], "TEARDOWN_PENDING")
            if self._activation_transition_owner is not None:
                try:
                    if not self._activation_transition_owner.teardown(payload["request_id"]):
                        cleanup_error = "ACTIVATION_TEARDOWN_NOT_CONFIRMED"
                except Exception as exc:
                    cleanup_error = f"ACTIVATION_TEARDOWN_EXCEPTION:{type(exc).__name__}"
            try:
                if not self._binding_controller.teardown(binding):
                    cleanup_error = cleanup_error or "BINDING_TEARDOWN_NOT_CONFIRMED"
            except Exception as exc:
                cleanup_error = cleanup_error or f"BINDING_TEARDOWN_EXCEPTION:{type(exc).__name__}"

            if (
                activation_authorization is not None
                and self._activation_ceremony_coordinator is not None
            ):
                try:
                    self._activation_ceremony_coordinator.complete(
                        activation_authorization,
                        success=(
                            result is not None
                            and result.decision == "ALLOW"
                            and cleanup_error is None
                            and not activation_recovery_required
                        ),
                    )
                except Exception:
                    cleanup_error = cleanup_error or "CEREMONY_AUDIT_PERSISTENCE_FAILURE"

            if self._recovery_store is not None:
                if cleanup_error is None and not activation_recovery_required:
                    self._recovery_store.mark_clean(payload["request_id"])
                else:
                    self._recovery_store.transition(
                        payload["request_id"],
                        "RECOVERY_REQUIRED",
                        cleanup_state="PENDING",
                    )

        if cleanup_error is not None:
            return self._deny(cleanup_error)
        if action_error is not None:
            return self._deny(f"GOVERNED_ACTION_EXCEPTION:{type(action_error).__name__}")
        if result is None:
            return self._deny("MISSING_GOVERNED_ACTION_RESULT")
        return result

    @staticmethod
    def _deny(reason: str) -> ProductionAppHostResult:
        return ProductionAppHostResult(decision="DENY", reason=reason)
