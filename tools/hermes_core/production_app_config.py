"""EA-4E.43 non-live outer feature-gate configuration injection.

CONFIGURATION != USER REQUEST != ACTIVATION != EXECUTION.

Explicit constructor/deployment config only. Default DISABLED.
No env, CLI, task-text, or request-field enablement.
Does not mutate master enable, activation, receiver, authority, binding, or store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.hermes_core.production_app_callsite import REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT
from tools.hermes_core.production_app_factory import ProductionAppFactoryConfig
from tools.hermes_core.production_executor_binding import ExecutorRegistry
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_wiring import (
    FORBIDDEN_GROK_RECEIVERS,
    ProductionWiringConfig,
)


FEATURE_GATE_ALLOWED_VALUES = frozenset({"DISABLED", "ENABLED"})
APPLICATION_FEATURE_GATE_DEFAULT = REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT


class ProductionAppConfigError(RuntimeError):
    """Fail-closed application/deployment config error."""

    def __init__(self, reason: str, *, detail: str = "") -> None:
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class ProductionAppRuntimeConfig:
    """Explicit application/deployment config. Immutable. Not request data."""

    wiring: ProductionWiringConfig
    clock: ClockCollaborator | None = None
    callsite_feature_gate: str | None = APPLICATION_FEATURE_GATE_DEFAULT
    executor_registry: ExecutorRegistry | None = None
    register_real_executors: bool = False
    recovery_store_path: Path | None = None
    recovery_host_instance_id: str | None = None
    recovery_liveness_inspector: object | None = None
    recovery_process_controller: object | None = None
    credential_preflight: object | None = None
    accounting_ledger: object | None = None


def canonicalize_feature_gate(value: object) -> str:
    if value is None:
        return APPLICATION_FEATURE_GATE_DEFAULT
    if type(value) is not str:
        raise ProductionAppConfigError("INVALID_FEATURE_GATE_VALUE")
    if value not in FEATURE_GATE_ALLOWED_VALUES:
        raise ProductionAppConfigError("INVALID_FEATURE_GATE_VALUE")
    return value


def build_factory_config(
    runtime_config: ProductionAppRuntimeConfig | None,
) -> ProductionAppFactoryConfig:
    if runtime_config is None:
        raise ProductionAppConfigError("MISSING_CONFIG_OBJECT")
    gate = canonicalize_feature_gate(runtime_config.callsite_feature_gate)
    if runtime_config.wiring.receiver_id in FORBIDDEN_GROK_RECEIVERS:
        raise ProductionAppConfigError("GROK_CONFIGURATION")
    return ProductionAppFactoryConfig(
        wiring=runtime_config.wiring,
        clock=runtime_config.clock,
        callsite_feature_gate=gate,
        executor_registry=runtime_config.executor_registry,
        register_real_executors=runtime_config.register_real_executors,
        credential_preflight=runtime_config.credential_preflight,
        accounting_ledger=runtime_config.accounting_ledger,
    )
