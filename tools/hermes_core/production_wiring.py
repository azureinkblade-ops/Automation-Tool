"""EA-4E.35 non-live production composition root.

WIRE != ENABLE.

This module assembles the already-qualified Kilo 7.5.15 + OpenCode governed
chain for the real application runtime without enabling production execution.

It does not:
- select a default receiver;
- issue execution authority at import/startup;
- issue invocation authorization at import/startup;
- bind executors automatically;
- start receiver processes;
- retry, fall back, fail over, or route to Grok;
- open or create automation_state.db;
- initialize a missing established durable store.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableAuthorizationStoreUnavailable,
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.governed_bound_executor import GovernedBoundExecutorResolver
from tools.hermes_core.governed_production_caller import (
    GovernedProductionCaller,
    GovernedProductionCallerRequest,
    GovernedProductionCallerResult,
)
from tools.hermes_core.governed_production_runtime import GovernedProductionRuntime
from tools.hermes_core.kilo_adapter import PINNED_KILO_PATH
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import PINNED_OPENCODE_PATH
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_activation import ProductionActivationValidator
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingPolicy,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.receiver_dispatch import ExecutionAuthorityValidator
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    ReceiverRouter,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)


SUPPORTED_PRODUCTION_RECEIVERS = frozenset({"kilo-cli-agent", "opencode-cli-agent"})
FORBIDDEN_GROK_RECEIVERS = frozenset(
    {
        "grok",
        "grok-cli",
        "grok-cli-agent",
        "xai",
        "xai-grok",
        "grok-provider",
    }
)

_HERMES_APP_DATA = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\David\AppData\Local"))
DEFAULT_PRODUCTION_AUTH_STORE_PATH = (
    _HERMES_APP_DATA
    / "Hermes"
    / "runtime"
    / "ea4e"
    / "production"
    / "invocation-authorization.sqlite3"
)
DEFAULT_PRODUCTION_AUTH_ANCHOR_PATH = (
    _HERMES_APP_DATA
    / "Hermes"
    / "runtime"
    / "ea4e"
    / "production"
    / "invocation-authorization.anchor.json"
)

EA4E_PRODUCTION_CONFIG_KEYS = (
    "master_enable",
    "production_activation_default",
    "default_receiver",
    "receiver_id",
    "auth_store_path",
    "auth_anchor_path",
    "kilo_executable_path",
    "opencode_executable_path",
    "authority_ttl_seconds",
    "runtime_scope",
)


class ProductionWiringError(RuntimeError):
    """Fail-closed production wiring error."""

    def __init__(self, reason: str, *, detail: str = "") -> None:
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class ProductionWiringConfig:
    """Explicit production wiring configuration. Defaults keep execution disabled."""

    master_enable: str = "DISABLED"
    production_activation_default: str = "DISABLED"
    default_receiver: str = "NONE"
    receiver_id: str | None = None
    auth_store_path: Path = DEFAULT_PRODUCTION_AUTH_STORE_PATH
    auth_anchor_path: Path = DEFAULT_PRODUCTION_AUTH_ANCHOR_PATH
    kilo_executable_path: str = PINNED_KILO_PATH
    opencode_executable_path: str = PINNED_OPENCODE_PATH
    authority_ttl_seconds: int = 300
    runtime_scope: str = "production"


@dataclass
class ProductionComposition:
    """Assembled production collaborators. Invoke is gated by master_enable."""

    config: ProductionWiringConfig
    store: DurableInvocationAuthorizationStore
    router: ReceiverRouter
    caller: GovernedProductionCaller
    runtime: GovernedProductionRuntime
    issuer: ProductionInvocationAuthorizationIssuer
    resolver: GovernedBoundExecutorResolver
    binding_controller: ProductionExecutorBindingController
    executor_registry: ExecutorRegistry
    authority_validator: ExecutionAuthorityValidator
    activation_validator: ProductionActivationValidator
    clock: ClockCollaborator
    credential_preflight: object | None = None
    accounting_ledger: object | None = None

    def invoke(
        self, request: GovernedProductionCallerRequest
    ) -> GovernedProductionCallerResult:
        if self.config.master_enable != "ENABLED":
            return GovernedProductionCallerResult(
                caller_decision="DENY",
                caller_reason="PRODUCTION_MASTER_ENABLE_DISABLED",
            )
        if self.config.production_activation_default != "ENABLED":
            return GovernedProductionCallerResult(
                caller_decision="DENY",
                caller_reason="PRODUCTION_ACTIVATION_DISABLED",
            )
        receiver_id = request.runtime_request.receiver_id
        denied = classify_receiver(receiver_id)
        if denied is not None:
            return GovernedProductionCallerResult(
                caller_decision="DENY",
                caller_reason=denied,
            )
        return self.caller.invoke(request)


def classify_receiver(receiver_id: str | None) -> str | None:
    if receiver_id is None or not str(receiver_id).strip():
        return "MISSING_RECEIVER"
    if receiver_id in FORBIDDEN_GROK_RECEIVERS:
        return "UNSUPPORTED_RECEIVER"
    if receiver_id not in SUPPORTED_PRODUCTION_RECEIVERS:
        return "UNSUPPORTED_RECEIVER"
    return None


def verify_frozen_executor_paths(config: ProductionWiringConfig) -> None:
    if config.kilo_executable_path != PINNED_KILO_PATH:
        raise ProductionWiringError("EXECUTABLE_BINDING_MISMATCH")
    if config.opencode_executable_path != PINNED_OPENCODE_PATH:
        raise ProductionWiringError("EXECUTABLE_BINDING_MISMATCH")


def open_production_auth_store(
    config: ProductionWiringConfig,
) -> DurableInvocationAuthorizationStore:
    """Reopen an established store. Missing store/anchor fails closed."""
    if Path(config.auth_store_path).name == "automation_state.db":
        raise ProductionWiringError("AUTOMATION_STATE_DB_FORBIDDEN")
    try:
        return DurableInvocationAuthorizationStore(
            config.auth_store_path, anchor_path=config.auth_anchor_path
        )
    except DurableAuthorizationStoreUnavailable as exc:
        message = str(exc)
        if "anchor" in message.lower():
            raise ProductionWiringError("ANCHOR_MISSING_OR_INVALID", detail=message) from exc
        raise ProductionWiringError("AUTH_STORE_MISSING", detail=message) from exc


def initialize_production_auth_store(
    config: ProductionWiringConfig,
) -> DurableInvocationAuthorizationStore:
    """Explicit fresh-install initialization. Never called by assemble()."""
    if Path(config.auth_store_path).name == "automation_state.db":
        raise ProductionWiringError("AUTOMATION_STATE_DB_FORBIDDEN")
    return DurableInvocationAuthorizationStore.initialize(
        config.auth_store_path, anchor_path=config.auth_anchor_path
    )


def register_qualified_real_executors(
    registry: ExecutorRegistry,
    *,
    config: ProductionWiringConfig,
) -> ExecutorRegistry:
    """Register frozen real executors. Does not bind, issue, or execute."""
    verify_frozen_executor_paths(config)
    if not registry.has_executor("kilo-cli-agent"):
        registry.register(
            "kilo-cli-agent",
            RealKiloProductionExecutor(kilo_executable=config.kilo_executable_path),
        )
    if not registry.has_executor("opencode-cli-agent"):
        registry.register("opencode-cli-agent", RealOpenCodeProductionExecutor())
    return registry


def assemble_production_composition(
    config: ProductionWiringConfig,
    *,
    clock: ClockCollaborator,
    executor_registry: Optional[ExecutorRegistry] = None,
    register_real_executors: bool = True,
    credential_preflight=None,
    accounting_ledger=None,
) -> ProductionComposition:
    """Compose production collaborators. Does not enable execution or bind."""
    if config.master_enable not in ("DISABLED", "ENABLED"):
        raise ProductionWiringError("INVALID_MASTER_ENABLE")
    if config.production_activation_default not in ("DISABLED", "ENABLED"):
        raise ProductionWiringError("INVALID_PRODUCTION_ACTIVATION_DEFAULT")
    if config.default_receiver != "NONE":
        raise ProductionWiringError("DEFAULT_RECEIVER_FORBIDDEN")
    if config.receiver_id is not None:
        denied = classify_receiver(config.receiver_id)
        if denied is not None:
            raise ProductionWiringError(denied)
    verify_frozen_executor_paths(config)
    store = open_production_auth_store(config)
    registry = executor_registry or ExecutorRegistry()
    if register_real_executors:
        register_qualified_real_executors(registry, config=config)
    binding_clock = BindingClock(now=clock.now_iso())
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=binding_clock),
        clock=binding_clock,
    )
    if credential_preflight is None:
        from tools.hermes_core.production_credential_preflight import (
            ProductionCredentialReadinessPreflight,
        )

        credential_preflight = ProductionCredentialReadinessPreflight()
    if accounting_ledger is None:
        from tools.hermes_core.production_accounting import ProductionAccountingLedger

        accounting_path = Path(config.auth_store_path).with_name(
            "production-accounting.sqlite3"
        )
        accounting_ledger = ProductionAccountingLedger.initialize(accounting_path)
    runtime = GovernedProductionRuntime(
        clock=clock,
        executor_registry=registry,
        binding_controller=controller,
        invocation_authorization_store=store,
        accounting_ledger=accounting_ledger,
    )
    resolver = GovernedBoundExecutorResolver(
        binding_controller=controller,
        executor_registry=registry,
        clock=binding_clock,
    )
    issuer = ProductionInvocationAuthorizationIssuer(clock=clock, store=store)
    caller = GovernedProductionCaller(
        resolver=resolver, issuer=issuer, runtime=runtime
    )
    router = get_default_router()
    return ProductionComposition(
        config=config,
        store=store,
        router=router,
        caller=caller,
        runtime=runtime,
        issuer=issuer,
        resolver=resolver,
        binding_controller=controller,
        executor_registry=registry,
        authority_validator=ExecutionAuthorityValidator(
            router_contract_id=compute_ea4e6_router_contract_id(),
            now=clock.now_iso(),
        ),
        activation_validator=ProductionActivationValidator(
            router_contract_id=compute_ea4e6_router_contract_id(),
        ),
        clock=clock,
        credential_preflight=credential_preflight,
        accounting_ledger=accounting_ledger,
    )


def route_explicit_receiver(receiver_id: str):
    denied = classify_receiver(receiver_id)
    if denied is not None:
        return denied, None
    return None, get_default_router().route(RoutingRequest(receiver_id=receiver_id))


def production_wiring_contract_snapshot() -> dict[str, object]:
    """Non-sealed documentation snapshot. Not part of the 13-artifact roll."""
    return {
        "wire_equals_enable": False,
        "master_enable_default": "DISABLED",
        "production_activation_default": "DISABLED",
        "default_receiver": "NONE",
        "supported_receivers": sorted(SUPPORTED_PRODUCTION_RECEIVERS),
        "forbidden_grok_receivers": sorted(FORBIDDEN_GROK_RECEIVERS),
        "auth_store_default": str(DEFAULT_PRODUCTION_AUTH_STORE_PATH),
        "auth_anchor_default": str(DEFAULT_PRODUCTION_AUTH_ANCHOR_PATH),
        "automation_state_db_used": False,
        "kilo_executable": PINNED_KILO_PATH,
        "opencode_executable": PINNED_OPENCODE_PATH,
        "qualified_receivers": sorted(QUALIFIED_RECEIVERS),
        "fallback": False,
        "failover": False,
        "automatic_retry": False,
        "auto_reissue": False,
        "scheduler_integration": False,
        "cron_integration": False,
        "app_py_integration": False,
        "config_keys": list(EA4E_PRODUCTION_CONFIG_KEYS),
    }
