"""EA-4E.45 non-live explicit executor binding provisioning path.

BINDING REQUEST != BINDING != EXECUTION.

Wraps ProductionExecutorBindingController.bind.
Requires a pre-registered fake/qualified executor identity.
Does not construct or register real executors.
Does not auto-bind on import, startup, factory, or user action.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tools.hermes_core.production_executor_binding import (
    BindingPolicyError,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingHandle,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_issuance import ALLOWED_DELEGATION_CLASS, QUALIFIED_RECEIVERS
from tools.hermes_core.production_wiring import classify_receiver


class ProductionAppBindingError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ProductionAppBindingRequest:
    enablement_id: str | None
    receiver_id: str | None
    executor_id: str | None
    executor_factory: str | None
    transport_contract_id: str | None
    model_binding_id: str | None
    runtime_scope: str | None
    issued_at: str | None
    expires_at: str | None
    requested_ttl_seconds: int | None
    request_nonce: str | None
    delegation_class: str | None


@dataclass(frozen=True)
class ProductionAppBindingResult:
    binding_decision: str
    binding_reason: str
    handle: ProductionExecutorBindingHandle | None = None
    constructed_receiver_id: str | None = None
    constructed_executor_id: str | None = None
    constructed_transport_id: str | None = None
    constructed_model_binding_id: str | None = None
    constructed_scope: str | None = None


class ProductionAppBindingProvisioner:
    """Stateless except for injected controller and registry."""

    def __init__(
        self,
        controller: ProductionExecutorBindingController | None,
        registry: ExecutorRegistry | None,
        preflight: object | None = None,
    ) -> None:
        self._controller = controller
        self._registry = registry
        self._preflight = preflight

    def bind(self, request: ProductionAppBindingRequest | None) -> ProductionAppBindingResult:
        if self._controller is None:
            return self._deny("MISSING_BINDING_CONTROLLER")
        if self._registry is None:
            return self._deny("MISSING_EXECUTOR_REGISTRY")
        if request is None:
            return self._deny("MISSING_REQUEST")
        if not request.enablement_id or not str(request.enablement_id).strip():
            return self._deny("MISSING_ENABLEMENT_ID")
        denied = classify_receiver(request.receiver_id)
        if denied is not None:
            return self._deny(denied)
        if not request.executor_id or not str(request.executor_id).strip():
            return self._deny("MISSING_EXECUTOR_ID")
        if not request.executor_factory or not str(request.executor_factory).strip():
            return self._deny("MISSING_EXECUTOR_FACTORY")
        if not request.transport_contract_id or not str(request.transport_contract_id).strip():
            return self._deny("INVALID_TRANSPORT")
        if not request.model_binding_id or not str(request.model_binding_id).strip():
            return self._deny("INVALID_MODEL_BINDING")
        if request.runtime_scope is None or not str(request.runtime_scope).strip():
            return self._deny("INVALID_SCOPE")
        if request.delegation_class is None or not str(request.delegation_class).strip():
            return self._deny("INVALID_DELEGATION_CLASS")
        if not request.issued_at or not request.expires_at:
            return self._deny("INVALID_EXPIRY")
        if request.requested_ttl_seconds is None or request.requested_ttl_seconds <= 0:
            return self._deny("INVALID_TTL")
        if not request.request_nonce or not str(request.request_nonce).strip():
            return self._deny("MISSING_NONCE")

        qualified = QUALIFIED_EXECUTOR_IMPLEMENTATIONS.get(request.receiver_id, {})
        qualified_identities = {
            spec["executor_identity"] for spec in QUALIFIED_EXECUTOR_IMPLEMENTATIONS.values()
        }
        if request.executor_id not in qualified_identities:
            return self._deny("UNQUALIFIED_EXECUTOR")
        if request.executor_id != qualified.get("executor_identity"):
            return self._deny("EXECUTOR_IDENTITY_MISMATCH")
        if request.executor_factory != qualified.get("executor_factory"):
            return self._deny("EXECUTOR_FACTORY_MISMATCH")
        if request.transport_contract_id != QUALIFIED_RECEIVERS[request.receiver_id][
            "transport_contract_id"
        ]:
            return self._deny("TRANSPORT_CONTRACT_MISMATCH")
        if request.model_binding_id != QUALIFIED_RECEIVERS[request.receiver_id]["model_binding_id"]:
            return self._deny("MODEL_BINDING_MISMATCH")
        if request.runtime_scope != "production":
            return self._deny("UNSUPPORTED_RUNTIME_SCOPE")
        if request.delegation_class != ALLOWED_DELEGATION_CLASS:
            return self._deny("DELEGATION_CLASS_MISMATCH")

        if not self._registry.has_executor(request.receiver_id):
            return self._deny("EXECUTOR_NOT_REGISTERED")
        existing = self._registry.resolve(request.receiver_id)
        if existing is None or getattr(existing, "executor_id", None) != request.executor_id:
            return self._deny("EXECUTOR_NOT_REGISTERED")

        if self._preflight is not None:
            preflight_result = self._preflight.check(
                self._preflight.config_for(
                    request.receiver_id,
                    transport_contract_id=request.transport_contract_id,
                    model_binding_id=request.model_binding_id,
                )
            )
            if not preflight_result.ready:
                return self._deny(
                    f"CREDENTIAL_PREFLIGHT_DENIED:{preflight_result.failure_code}"
                )

        enablement = ProductionExecutorBindingEnablement(
            enablement_id=request.enablement_id,
            receiver_id=request.receiver_id,
            transport_contract_id=request.transport_contract_id,
            model_binding_id=request.model_binding_id,
            executor_identity=request.executor_id,
            executor_factory=request.executor_factory,
            runtime_scope=request.runtime_scope,
            issued_at=request.issued_at,
            expires_at=request.expires_at,
            delegation_class=request.delegation_class,
            requested_ttl_seconds=Decimal(str(request.requested_ttl_seconds)),
            request_nonce=request.request_nonce,
        )
        preserved = {
            "constructed_receiver_id": enablement.receiver_id,
            "constructed_executor_id": enablement.executor_identity,
            "constructed_transport_id": enablement.transport_contract_id,
            "constructed_model_binding_id": enablement.model_binding_id,
            "constructed_scope": enablement.runtime_scope,
        }
        prior_handle = self._controller.get_bound_handle(request.enablement_id)
        try:
            handle = self._controller.bind(
                enablement,
                self._registry,
                executor_factory=lambda: existing,
            )
        except BindingPolicyError as exc:
            reason = exc.reason
            return ProductionAppBindingResult(
                binding_decision="DENY",
                binding_reason=reason,
                **preserved,
            )
        except Exception as exc:
            return ProductionAppBindingResult(
                binding_decision="DENY",
                binding_reason=f"CONTROLLER_EXCEPTION:{type(exc).__name__}",
                **preserved,
            )
        if prior_handle is not None:
            return ProductionAppBindingResult(
                binding_decision="ALREADY_BOUND",
                binding_reason="IDENTICAL_DUPLICATE",
                handle=handle,
                **preserved,
            )
        return ProductionAppBindingResult(
            binding_decision="BOUND",
            binding_reason="POLICY_ALLOW",
            handle=handle,
            **preserved,
        )

    @staticmethod
    def _deny(reason: str) -> ProductionAppBindingResult:
        return ProductionAppBindingResult(
            binding_decision="DENY",
            binding_reason=reason,
        )
