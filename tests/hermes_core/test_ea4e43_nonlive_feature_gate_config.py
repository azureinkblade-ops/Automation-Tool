"""EA-4E.43 non-live outer feature-gate configuration injection. Fake only."""

from __future__ import annotations

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_config import (
    APPLICATION_FEATURE_GATE_DEFAULT,
    ProductionAppConfigError,
    ProductionAppRuntimeConfig,
    build_factory_config,
)
from tools.hermes_core.production_app_factory import ProductionAppFactory
from tools.hermes_core.production_app_user_action import (
    ProductionAppUserActionRequest,
)
from tools.hermes_core.production_execution import ProductionExecutorResult
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingEnablement,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_wiring import (
    ProductionWiringConfig,
    initialize_production_auth_store,
)


NOW = "2026-01-01T00:00:00Z"
TRIPWIRE_HITS = {
    "executor": 0,
    "adapter": 0,
    "process": 0,
    "model": 0,
    "auth": 0,
    "invocation": 0,
    "store_init": 0,
}


class FakeExecutor:
    def __init__(self, receiver_id):
        self.receiver_id = receiver_id
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
        self.call_count = 0

    def execute(self, request):
        self.call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E43_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(
        executor=0, adapter=0, process=0, model=0, auth=0, invocation=0, store_init=0
    )

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E43_REAL_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", trip("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", trip("process"))
    original_issue = ProductionInvocationAuthorizationIssuer.issue

    def spy_issue(self, *args, **kwargs):
        TRIPWIRE_HITS["invocation"] += 1
        return original_issue(self, *args, **kwargs)

    monkeypatch.setattr(ProductionInvocationAuthorizationIssuer, "issue", spy_issue)
    original_initialize = DurableInvocationAuthorizationStore.initialize

    def guarded_initialize(*args, **kwargs):
        TRIPWIRE_HITS["store_init"] += 1
        return original_initialize(*args, **kwargs)

    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", guarded_initialize)
    yield TRIPWIRE_HITS
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["model"] == 0


def wiring(tmp_path, **changes) -> ProductionWiringConfig:
    return ProductionWiringConfig(
        auth_store_path=tmp_path / "invocation-authorization.sqlite3",
        auth_anchor_path=tmp_path / "invocation-authorization.anchor.json",
        **changes,
    )


def established(tmp_path, **changes) -> ProductionWiringConfig:
    cfg = wiring(tmp_path, **changes)
    TRIPWIRE_HITS["store_init"] = 0
    initialize_production_auth_store(cfg)
    TRIPWIRE_HITS["store_init"] = 0
    return cfg


def runtime(tmp_path, **changes) -> ProductionAppRuntimeConfig:
    fields = {
        "wiring": established(tmp_path),
        "clock": ClockCollaborator(now=NOW),
        "register_real_executors": False,
    }
    fields.update(changes)
    return ProductionAppRuntimeConfig(**fields)


def bind_fake(composition, receiver_id="kilo-cli-agent"):
    clock = BindingClock(now=NOW)
    info = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    receiver = QUALIFIED_RECEIVERS[receiver_id]
    fake = composition.executor_registry.resolve(receiver_id)
    enablement = ProductionExecutorBindingEnablement(
        enablement_id=f"enablement-{receiver_id}",
        receiver_id=receiver_id,
        transport_contract_id=receiver["transport_contract_id"],
        model_binding_id=receiver["model_binding_id"],
        executor_identity=info["executor_identity"],
        executor_factory=info["executor_factory"],
        runtime_scope="production",
        issued_at=clock.now_iso(),
        expires_at=clock.now_plus_seconds(3600),
        delegation_class="governed",
        requested_ttl_seconds=3600,
        max_bound_executors=1,
        enabled=True,
        request_nonce=f"binding-nonce-{receiver_id}",
    )
    composition.binding_controller.bind(
        enablement, ExecutorRegistry(), executor_factory=lambda: fake
    )
    return fake


def issue_request(receiver_id, request_id, composition):
    handle = composition.binding_controller.get_binding_for_receiver(receiver_id)
    return ProductionInvocationAuthorizationIssueRequest(
        issue_request_id=f"issue-{request_id}",
        execution_request_id=request_id,
        receiver_id=receiver_id,
        binding_id=handle.binding_id,
        enablement_id=handle.enablement_id,
        nonce=f"nonce-{request_id}",
    )


def test_user_action_request_has_no_feature_gate_field():
    assert "feature_gate" not in ProductionAppUserActionRequest.__dataclass_fields__
    assert "callsite_feature_gate" not in ProductionAppUserActionRequest.__dataclass_fields__


def test_missing_config_object():
    with pytest.raises(ProductionAppConfigError) as exc:
        build_factory_config(None)
    assert exc.value.reason == "MISSING_CONFIG_OBJECT"


def test_none_feature_gate_resolves_disabled(tmp_path):
    factory_cfg = build_factory_config(runtime(tmp_path, callsite_feature_gate=None))
    assert factory_cfg.callsite_feature_gate == "DISABLED"
    assert APPLICATION_FEATURE_GATE_DEFAULT == "DISABLED"


@pytest.mark.parametrize(
    "value",
    ["", "disabled", "enabled", True, False, 1, 0, "yes", "no", "on", "off", "maybe"],
)
def test_invalid_feature_gate_values(tmp_path, value):
    with pytest.raises(ProductionAppConfigError) as exc:
        build_factory_config(runtime(tmp_path, callsite_feature_gate=value))
    assert exc.value.reason == "INVALID_FEATURE_GATE_VALUE"


def test_grok_configuration_attempt(tmp_path):
    with pytest.raises(ProductionAppConfigError) as exc:
        build_factory_config(runtime(tmp_path, wiring=established(tmp_path, receiver_id="grok")))
    assert exc.value.reason == "GROK_CONFIGURATION"


def test_request_cannot_override_feature_gate():
    with pytest.raises(TypeError):
        ProductionAppUserActionRequest(
            request_id="x",
            receiver_id="kilo-cli-agent",
            feature_gate="ENABLED",
        )


def test_default_config_disables_callsite(tmp_path):
    factory_cfg = build_factory_config(runtime(tmp_path))
    assert factory_cfg.callsite_feature_gate == "DISABLED"
    components = ProductionAppFactory.build(factory_cfg)
    assert components.app_callsite._feature_gate == "DISABLED"
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-default",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert TRIPWIRE_HITS["invocation"] == 0
    assert TRIPWIRE_HITS["store_init"] == 0


def test_explicit_enabled_preserved_to_callsite(tmp_path):
    factory_cfg = build_factory_config(
        runtime(tmp_path, callsite_feature_gate="ENABLED")
    )
    assert factory_cfg.callsite_feature_gate == "ENABLED"
    components = ProductionAppFactory.build(factory_cfg)
    assert components.app_callsite._feature_gate == "ENABLED"


def test_enabled_gate_does_not_override_master(tmp_path):
    factory_cfg = build_factory_config(
        runtime(
            tmp_path,
            wiring=established(tmp_path, master_enable="DISABLED"),
            callsite_feature_gate="ENABLED",
        )
    )
    components = ProductionAppFactory.build(factory_cfg)
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-a",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"


def test_enabled_gate_does_not_override_activation(tmp_path):
    factory_cfg = build_factory_config(
        runtime(
            tmp_path,
            wiring=established(tmp_path, master_enable="ENABLED"),
            callsite_feature_gate="ENABLED",
        )
    )
    components = ProductionAppFactory.build(factory_cfg)
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-b",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=False,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"


def test_enabled_gate_does_not_select_receiver(tmp_path):
    factory_cfg = build_factory_config(
        runtime(
            tmp_path,
            wiring=established(tmp_path, master_enable="ENABLED"),
            callsite_feature_gate="ENABLED",
        )
    )
    components = ProductionAppFactory.build(factory_cfg)
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-c",
            receiver_id=None,
            production_activation_explicit=True,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "MISSING_RECEIVER"


def test_enabled_gate_rejects_grok_receiver(tmp_path):
    factory_cfg = build_factory_config(
        runtime(
            tmp_path,
            wiring=established(tmp_path, master_enable="ENABLED"),
            callsite_feature_gate="ENABLED",
        )
    )
    components = ProductionAppFactory.build(factory_cfg)
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-d",
            receiver_id="grok",
            production_activation_explicit=True,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "UNSUPPORTED_RECEIVER"


def test_rebuild_isolation(tmp_path_factory):
    a = ProductionAppFactory.build(
        build_factory_config(runtime(tmp_path_factory.mktemp("a"), callsite_feature_gate="DISABLED"))
    )
    b = ProductionAppFactory.build(
        build_factory_config(runtime(tmp_path_factory.mktemp("b"), callsite_feature_gate="ENABLED"))
    )
    assert a.app_callsite._feature_gate == "DISABLED"
    assert b.app_callsite._feature_gate == "ENABLED"
    assert a.app_callsite is not b.app_callsite


def test_request_cannot_mutate_gate_for_later_request(tmp_path):
    components = ProductionAppFactory.build(build_factory_config(runtime(tmp_path)))
    first = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-r1",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
        )
    )
    assert first.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    second = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-r2",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
        )
    )
    assert second.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert components.app_callsite._feature_gate == "DISABLED"
    assert not hasattr(components.user_action, "set_feature_gate")
    assert not hasattr(components.app_callsite, "set_feature_gate")


def test_runtime_config_is_frozen(tmp_path):
    cfg = runtime(tmp_path)
    with pytest.raises(Exception):
        cfg.callsite_feature_gate = "ENABLED"


def test_no_env_loader_in_module():
    import inspect
    import tools.hermes_core.production_app_config as mod

    source = inspect.getsource(mod)
    assert "getenv" not in source
    assert "environ" not in source


def test_explicit_enabled_fake_kilo_path(tmp_path):
    registry = ExecutorRegistry()
    fake = FakeExecutor("kilo-cli-agent")
    registry.register("kilo-cli-agent", fake)
    components = ProductionAppFactory.build(
        build_factory_config(
            runtime(
                tmp_path,
                wiring=established(tmp_path, master_enable="ENABLED"),
                callsite_feature_gate="ENABLED",
                executor_registry=registry,
            )
        )
    )
    assert TRIPWIRE_HITS["invocation"] == 0
    bind_fake(components.composition, "kilo-cli-agent")
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e43-kilo",
            receiver_id="kilo-cli-agent",
            task_payload="EA4E43_FAKE_OK",
            production_activation_explicit=True,
            runtime_scope="production",
            authorization_issue_request=issue_request(
                "kilo-cli-agent", "ea4e43-kilo", components.composition
            ),
        )
    )
    assert result.user_action_decision == "ALLOW"
    assert fake.call_count == 1
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
