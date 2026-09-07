"""EA-4E.42 non-live lazy production application factory.

FACTORY != USER ACTION != EXECUTION.
CONSTRUCTION != ACTIVATION != AUTHORIZATION.

Explicit build only. No import/startup construction. No receiver start, model
call, authority issuance, invocation-auth issuance, executor binding, or
durable-store bootstrap. Missing established store fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.hermes_core.production_app_adapter import ProductionAppAdapter
from tools.hermes_core.production_app_callsite import (
    REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT,
    ProductionAppCallSite,
)
from tools.hermes_core.production_app_user_action import ProductionAppUserAction
from tools.hermes_core.production_application_caller import ProductionApplicationCaller
from tools.hermes_core.production_entrypoint import (
    ProductionEntryPoint,
    build_production_entrypoint,
)
from tools.hermes_core.production_executor_binding import ExecutorRegistry
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_wiring import (
    ProductionComposition,
    ProductionWiringConfig,
    ProductionWiringError,
    assemble_production_composition,
    classify_receiver,
)


class ProductionAppFactoryError(RuntimeError):
    """Fail-closed lazy factory error."""

    def __init__(self, reason: str, *, detail: str = "") -> None:
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class ProductionAppFactoryConfig:
    wiring: ProductionWiringConfig
    clock: ClockCollaborator | None = None
    callsite_feature_gate: str = REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT
    executor_registry: ExecutorRegistry | None = None
    register_real_executors: bool = False


@dataclass(frozen=True)
class ProductionAppComponents:
    composition: ProductionComposition
    entrypoint: ProductionEntryPoint
    application_caller: ProductionApplicationCaller
    app_adapter: ProductionAppAdapter
    app_callsite: ProductionAppCallSite
    user_action: ProductionAppUserAction


class ProductionAppFactory:
    """Explicit lazy builder. Stateless. No module-global cache."""

    @staticmethod
    def build(config: ProductionAppFactoryConfig | None) -> ProductionAppComponents:
        if config is None:
            raise ProductionAppFactoryError("MISSING_REQUIRED_CONFIG")
        if config.clock is None:
            raise ProductionAppFactoryError("MISSING_REQUIRED_COLLABORATOR")
        if config.callsite_feature_gate not in ("DISABLED", "ENABLED"):
            raise ProductionAppFactoryError("INVALID_CALLSITE_FEATURE_GATE_VALUE")
        if config.executor_registry is not None and not isinstance(
            config.executor_registry, ExecutorRegistry
        ):
            raise ProductionAppFactoryError("INVALID_EXECUTOR_REGISTRY")
        wiring = config.wiring
        if wiring.master_enable not in ("DISABLED", "ENABLED"):
            raise ProductionAppFactoryError("INVALID_MASTER_ENABLE_VALUE")
        store_path = Path(wiring.auth_store_path)
        anchor_path = Path(wiring.auth_anchor_path)
        if not str(store_path).strip() or store_path.name in ("", ".", ".."):
            raise ProductionAppFactoryError("INVALID_AUTH_STORE_PATH")
        if not str(anchor_path).strip() or anchor_path.name in ("", ".", ".."):
            raise ProductionAppFactoryError("INVALID_AUTH_ANCHOR_PATH")
        if Path(wiring.auth_store_path).name == "automation_state.db":
            raise ProductionAppFactoryError("AUTOMATION_STATE_DB_FORBIDDEN")
        if wiring.receiver_id is not None:
            denied = classify_receiver(wiring.receiver_id)
            if denied is not None:
                reason = (
                    "GROK_CONFIGURATION"
                    if wiring.receiver_id
                    in {
                        "grok",
                        "grok-cli",
                        "grok-cli-agent",
                        "xai",
                        "xai-grok",
                        "grok-provider",
                    }
                    else "UNSUPPORTED_RECEIVER_CONFIGURATION"
                )
                raise ProductionAppFactoryError(reason)
        try:
            composition = assemble_production_composition(
                wiring,
                clock=config.clock,
                executor_registry=config.executor_registry,
                register_real_executors=config.register_real_executors,
            )
        except ProductionWiringError as exc:
            mapped = {
                "INVALID_MASTER_ENABLE": "INVALID_MASTER_ENABLE_VALUE",
                "AUTH_STORE_MISSING": "MISSING_ESTABLISHED_AUTH_STORE",
                "ANCHOR_MISSING_OR_INVALID": "INVALID_AUTH_ANCHOR_PATH",
            }.get(exc.reason, exc.reason)
            raise ProductionAppFactoryError(mapped, detail=str(exc)) from exc
        entrypoint = build_production_entrypoint(composition)
        application_caller = ProductionApplicationCaller(entrypoint)
        app_adapter = ProductionAppAdapter(application_caller)
        app_callsite = ProductionAppCallSite(
            app_adapter, feature_gate=config.callsite_feature_gate
        )
        user_action = ProductionAppUserAction(app_callsite)
        return ProductionAppComponents(
            composition=composition,
            entrypoint=entrypoint,
            application_caller=application_caller,
            app_adapter=app_adapter,
            app_callsite=app_callsite,
            user_action=user_action,
        )
