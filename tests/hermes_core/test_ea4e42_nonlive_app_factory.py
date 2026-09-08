"""EA-4E.42 non-live lazy composition factory. Fake executors only."""

from __future__ import annotations

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_factory import (
    ProductionAppComponents,
    ProductionAppFactory,
    ProductionAppFactoryConfig,
    ProductionAppFactoryError,
)
from tools.hermes_core.production_app_user_action import ProductionAppUserActionRequest
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
            output="EA4E42_FAKE_OK",
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
            raise AssertionError(f"EA4E42_REAL_{category.upper()}_TRIPWIRE")

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


def factory_config(tmp_path, *, established_store=True, **changes):
    wiring_cfg = established(tmp_path) if established_store else wiring(tmp_path)
    fields = {
        "wiring": wiring_cfg,
        "clock": ClockCollaborator(now=NOW),
        "callsite_feature_gate": "DISABLED",
        "register_real_executors": False,
    }
    fields.update(changes)
    return ProductionAppFactoryConfig(**fields)


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


def test_import_has_no_side_effects():
    import tools.hermes_core.production_app_factory as mod

    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["invocation"] == 0
    assert TRIPWIRE_HITS["store_init"] == 0
    assert getattr(mod, "_COMPONENTS", None) is None
    assert getattr(mod, "_CACHE", None) is None
    assert not hasattr(mod, "BUILT_COMPONENTS")


def test_missing_required_config():
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(None)
    assert exc.value.reason == "MISSING_REQUIRED_CONFIG"


def test_missing_clock_collaborator(tmp_path):
    cfg = factory_config(tmp_path, clock=None)
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "MISSING_REQUIRED_COLLABORATOR"


def test_invalid_master_enable(tmp_path):
    cfg = factory_config(
        tmp_path, wiring=established(tmp_path, master_enable="YES")
    )
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "INVALID_MASTER_ENABLE_VALUE"


def test_invalid_callsite_feature_gate(tmp_path):
    cfg = factory_config(tmp_path, callsite_feature_gate="ON")
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "INVALID_CALLSITE_FEATURE_GATE_VALUE"


def test_missing_established_auth_store(tmp_path):
    cfg = factory_config(tmp_path, established_store=False)
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "MISSING_ESTABLISHED_AUTH_STORE"
    assert not (tmp_path / "invocation-authorization.sqlite3").exists()
    assert TRIPWIRE_HITS["store_init"] == 0


def test_invalid_auth_store_path(tmp_path):
    cfg = factory_config(
        tmp_path,
        wiring=established(tmp_path).__class__(
            auth_store_path="",
            auth_anchor_path=tmp_path / "invocation-authorization.anchor.json",
        ),
    )
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "INVALID_AUTH_STORE_PATH"


def test_invalid_auth_anchor_path(tmp_path):
    cfg = factory_config(
        tmp_path,
        wiring=ProductionWiringConfig(
            auth_store_path=tmp_path / "invocation-authorization.sqlite3",
            auth_anchor_path="",
        ),
    )
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "INVALID_AUTH_ANCHOR_PATH"


def test_unsupported_receiver_configuration(tmp_path):
    cfg = factory_config(
        tmp_path, wiring=established(tmp_path, receiver_id="codex-cli-agent")
    )
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "UNSUPPORTED_RECEIVER_CONFIGURATION"


def test_grok_configuration(tmp_path):
    cfg = factory_config(tmp_path, wiring=established(tmp_path, receiver_id="grok"))
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "GROK_CONFIGURATION"


def test_invalid_executor_registry(tmp_path):
    cfg = factory_config(tmp_path, executor_registry=["not-a-registry"])
    with pytest.raises(ProductionAppFactoryError) as exc:
        ProductionAppFactory.build(cfg)
    assert exc.value.reason == "INVALID_EXECUTOR_REGISTRY"


def test_build_defaults_disabled_and_lazy(tmp_path):
    components = ProductionAppFactory.build(factory_config(tmp_path))
    assert isinstance(components, ProductionAppComponents)
    assert components.composition.config.master_enable == "DISABLED"
    assert components.composition.config.default_receiver == "NONE"
    assert components.app_callsite._feature_gate == "DISABLED"
    assert components.entrypoint.master_enable == "DISABLED"
    assert TRIPWIRE_HITS["store_init"] == 0
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["invocation"] == 0


def test_graph_integrity(tmp_path):
    components = ProductionAppFactory.build(factory_config(tmp_path))
    assert components.user_action._callsite is components.app_callsite
    assert components.app_callsite._adapter is components.app_adapter
    assert components.app_adapter._caller is components.application_caller
    assert components.application_caller._entrypoint is components.entrypoint
    assert components.entrypoint._composition is components.composition


def test_repeated_builds_isolated(tmp_path_factory):
    a_dir = tmp_path_factory.mktemp("a")
    b_dir = tmp_path_factory.mktemp("b")
    registry_a = ExecutorRegistry()
    registry_a.register("kilo-cli-agent", FakeExecutor("kilo-cli-agent"))
    registry_b = ExecutorRegistry()
    registry_b.register("opencode-cli-agent", FakeExecutor("opencode-cli-agent"))
    a = ProductionAppFactory.build(
        factory_config(a_dir, executor_registry=registry_a)
    )
    b = ProductionAppFactory.build(
        factory_config(b_dir, executor_registry=registry_b)
    )
    assert a is not b
    assert a.user_action is not b.user_action
    assert a.composition is not b.composition
    assert a.composition.executor_registry is not b.composition.executor_registry
    assert a.composition.store is not b.composition.store


def test_factory_does_not_bind_or_issue(tmp_path):
    registry = ExecutorRegistry()
    registry.register("kilo-cli-agent", FakeExecutor("kilo-cli-agent"))
    components = ProductionAppFactory.build(
        factory_config(tmp_path, executor_registry=registry)
    )
    assert (
        components.composition.binding_controller.get_binding_for_receiver(
            "kilo-cli-agent"
        )
        is None
    )
    assert TRIPWIRE_HITS["invocation"] == 0
    assert TRIPWIRE_HITS["store_init"] == 0


def test_kilo_fake_user_action_through_factory(tmp_path):
    registry = ExecutorRegistry()
    fake = FakeExecutor("kilo-cli-agent")
    registry.register("kilo-cli-agent", fake)
    components = ProductionAppFactory.build(
        factory_config(
            tmp_path,
            wiring=established(tmp_path, master_enable="ENABLED"),
            callsite_feature_gate="ENABLED",
            executor_registry=registry,
        )
    )
    assert TRIPWIRE_HITS["invocation"] == 0
    bind_fake(components.composition, "kilo-cli-agent")
    authority, activation = external_authority_and_activation(
        "kilo-cli-agent", "ea4e42-kilo"
    )
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e42-kilo",
            receiver_id="kilo-cli-agent",
            task_payload="EA4E42_FAKE_OK",
            production_activation_explicit=True,
            runtime_scope="production",
            authorization_issue_request=issue_request(
                "kilo-cli-agent", "ea4e42-kilo", components.composition
            ),
            execution_authority=authority,
            activation=activation,
        )
    )
    assert result.user_action_decision == "ALLOW"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert fake.call_count == 1
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0


def test_opencode_fake_user_action_through_factory(tmp_path):
    registry = ExecutorRegistry()
    fake = FakeExecutor("opencode-cli-agent")
    registry.register("opencode-cli-agent", fake)
    components = ProductionAppFactory.build(
        factory_config(
            tmp_path,
            wiring=established(tmp_path, master_enable="ENABLED"),
            callsite_feature_gate="ENABLED",
            executor_registry=registry,
        )
    )
    assert TRIPWIRE_HITS["invocation"] == 0
    bind_fake(components.composition, "opencode-cli-agent")
    authority, activation = external_authority_and_activation(
        "opencode-cli-agent", "ea4e42-oc"
    )
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e42-oc",
            receiver_id="opencode-cli-agent",
            task_payload="EA4E42_FAKE_OK",
            production_activation_explicit=True,
            runtime_scope="production",
            authorization_issue_request=issue_request(
                "opencode-cli-agent", "ea4e42-oc", components.composition
            ),
            execution_authority=authority,
            activation=activation,
        )
    )
    assert result.user_action_decision == "ALLOW"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert fake.call_count == 1
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
