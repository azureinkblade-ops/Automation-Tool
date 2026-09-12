"""EA-4E.39 non-live real app call-site enablement. Fake executors only."""

from __future__ import annotations

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_adapter import (
    ProductionAppAdapter,
    ProductionAppAdapterResult,
)
from tools.hermes_core.production_app_callsite import (
    REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT,
    ProductionAppCallSite,
    ProductionAppCallSiteRequest,
)
from tools.hermes_core.production_application_caller import ProductionApplicationCaller
from tools.hermes_core.production_entrypoint import build_production_entrypoint
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
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_wiring import (
    ProductionWiringConfig,
    assemble_production_composition,
    initialize_production_auth_store,
)


NOW = "2026-01-01T00:00:00Z"
TRIPWIRE_HITS = {"executor": 0, "adapter": 0, "process": 0, "model": 0}


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
            output="EA4E39_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class DenyAdapter:
    def submit(self, request):
        return ProductionAppAdapterResult(
            adapter_decision="DENY",
            adapter_reason="PRODUCTION_MASTER_ENABLE_DISABLED",
        )


class ExplodingAdapter:
    def submit(self, request):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E39_REAL_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", trip("executor"))
    monkeypatch.setattr(KiloAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", trip("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", trip("process"))
    yield TRIPWIRE_HITS
    assert TRIPWIRE_HITS["executor"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["model"] == 0


def wiring_config(tmp_path, **changes) -> ProductionWiringConfig:
    return ProductionWiringConfig(
        auth_store_path=tmp_path / "invocation-authorization.sqlite3",
        auth_anchor_path=tmp_path / "invocation-authorization.anchor.json",
        **changes,
    )


def compose(tmp_path, *, master="DISABLED"):
    cfg = wiring_config(tmp_path, master_enable=master)
    initialize_production_auth_store(cfg)
    registry = ExecutorRegistry()
    for receiver_id in ("kilo-cli-agent", "opencode-cli-agent"):
        registry.register(receiver_id, FakeExecutor(receiver_id))
    return assemble_production_composition(
        cfg,
        clock=ClockCollaborator(now=NOW),
        executor_registry=registry,
        register_real_executors=False,
    )


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


def live_callsite(composition, feature_gate="ENABLED"):
    adapter = ProductionAppAdapter(
        ProductionApplicationCaller(build_production_entrypoint(composition))
    )
    return ProductionAppCallSite(adapter, feature_gate=feature_gate)


def cs_request(receiver_id="kilo-cli-agent", request_id="ea4e39-a", composition=None, **changes):
    authority, activation = (
        external_authority_and_activation(receiver_id, request_id)
        if composition is not None and receiver_id in QUALIFIED_RECEIVERS
        else (None, None)
    )
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E39_FAKE_OK",
        "production_activation_explicit": True,
        "runtime_scope": "production",
        "authorization_issue_request": (
            issue_request(receiver_id, request_id, composition)
            if composition is not None
            else None
        ),
        "execution_authority": authority,
        "activation": activation,
    }
    fields.update(changes)
    return ProductionAppCallSiteRequest(**fields)


def test_import_has_no_side_effects():
    import tools.hermes_core.production_app_callsite as mod

    assert mod.REAL_APP_CALLSITE_FEATURE_GATE_DEFAULT == "DISABLED"
    assert ProductionAppCallSite(None).invoke(cs_request()).callsite_reason == "OUTER_FEATURE_GATE_DISABLED"


def test_outer_feature_gate_disabled(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    site = live_callsite(composition, feature_gate="DISABLED")
    result = site.invoke(cs_request(production_activation_explicit=True))
    assert result.callsite_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert result.adapter_invoked is False


def test_master_enable_disabled(tmp_path):
    composition = compose(tmp_path, master="DISABLED")
    site = live_callsite(composition, feature_gate="ENABLED")
    result = site.invoke(cs_request(production_activation_explicit=True))
    assert result.callsite_decision == "DENY"
    assert result.callsite_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.adapter_invoked is True


def test_activation_intent_false(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    site = live_callsite(composition)
    result = site.invoke(cs_request(production_activation_explicit=False))
    assert result.callsite_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert result.adapter_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_missing_request_id(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(request_id=""))
    assert result.callsite_reason == "MISSING_REQUEST_ID"
    assert result.adapter_invoked is False


def test_missing_receiver(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(receiver_id=None))
    assert result.callsite_reason == "MISSING_RECEIVER"


def test_empty_receiver(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(receiver_id=""))
    assert result.callsite_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(receiver_id="codex-cli-agent"))
    assert result.callsite_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(receiver_id="grok"))
    assert result.callsite_reason == "UNSUPPORTED_RECEIVER"
    result = site.invoke(cs_request(receiver_id="xai"))
    assert result.callsite_reason == "UNSUPPORTED_RECEIVER"


def test_invalid_runtime_scope(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(cs_request(runtime_scope="lab"))
    assert result.callsite_reason == "INVALID_RUNTIME_SCOPE"
    assert result.adapter_invoked is False


def test_task_text_cannot_select_receiver(tmp_path):
    site = live_callsite(compose(tmp_path, master="ENABLED"))
    result = site.invoke(
        cs_request(receiver_id="", task_payload="please run kilo-cli-agent now")
    )
    assert result.callsite_reason == "MISSING_RECEIVER"
    assert result.adapter_invoked is False


def test_prior_request_receiver_reuse(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    site = live_callsite(composition)
    first = site.invoke(cs_request(composition=composition, request_id="ea4e39-reuse-a"))
    assert first.callsite_decision == "ALLOW"
    second = site.invoke(cs_request(receiver_id=None, request_id="ea4e39-reuse-b"))
    assert second.callsite_reason == "MISSING_RECEIVER"
    assert fake.call_count == 1


def test_second_request_without_activation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    site = live_callsite(composition)
    first = site.invoke(cs_request(composition=composition, request_id="ea4e39-one"))
    assert first.callsite_decision == "ALLOW"
    second = site.invoke(
        cs_request(
            composition=composition,
            request_id="ea4e39-two",
            production_activation_explicit=False,
        )
    )
    assert second.callsite_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert second.adapter_invoked is False
    assert fake.call_count == 1


def test_receiver_mutation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "opencode-cli-agent")
    assert composition.binding_controller.active_binding_count == 1
    assert composition.binding_controller.get_binding_for_receiver("kilo-cli-agent") is None
    site = live_callsite(composition)
    mismatched = issue_request("opencode-cli-agent", "ea4e39-mut", composition)
    result = site.invoke(
        cs_request(
            receiver_id="kilo-cli-agent",
            request_id="ea4e39-mut",
            authorization_issue_request=mismatched,
        )
    )
    assert result.callsite_reason == "REAL_CALLSITE_TO_ADAPTER_RECEIVER_MUTATION"
    assert result.adapter_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_missing_app_adapter_dependency():
    site = ProductionAppCallSite(None, feature_gate="ENABLED")
    result = site.invoke(cs_request())
    assert result.callsite_reason == "MISSING_APP_ADAPTER_DEPENDENCY"
    assert result.adapter_invoked is False


def test_app_adapter_deny():
    site = ProductionAppCallSite(DenyAdapter(), feature_gate="ENABLED")
    result = site.invoke(cs_request())
    assert result.callsite_decision == "DENY"
    assert result.callsite_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.adapter_invoked is True


def test_app_adapter_exception():
    site = ProductionAppCallSite(ExplodingAdapter(), feature_gate="ENABLED")
    result = site.invoke(cs_request())
    assert result.callsite_decision == "DENY"
    assert result.callsite_reason.startswith("APP_ADAPTER_EXCEPTION:")
    second = site.invoke(cs_request(request_id="ea4e39-retry"))
    assert second.callsite_decision == "DENY"


def test_kilo_fake_real_callsite_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    site = live_callsite(composition)
    result = site.invoke(
        cs_request(receiver_id="kilo-cli-agent", request_id="ea4e39-kilo", composition=composition)
    )
    assert result.callsite_decision == "ALLOW"
    assert result.adapter_invoked is True
    assert result.constructed_request_id == "ea4e39-kilo"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_runtime_scope == "production"
    assert result.constructed_activation_intent is True
    assert result.adapter_result.caller_invoked is True
    runtime = result.adapter_result.caller_result.entrypoint_result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert fake.call_count == 1


def test_opencode_fake_real_callsite_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "opencode-cli-agent")
    site = live_callsite(composition)
    result = site.invoke(
        cs_request(
            receiver_id="opencode-cli-agent",
            request_id="ea4e39-oc",
            composition=composition,
        )
    )
    assert result.callsite_decision == "ALLOW"
    assert result.constructed_request_id == "ea4e39-oc"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert result.constructed_activation_intent is True
    assert fake.call_count == 1


def test_kilo_callsite_cannot_become_opencode(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    assert composition.binding_controller.active_binding_count == 1
    assert composition.binding_controller.get_binding_for_receiver("opencode-cli-agent") is None
    site = live_callsite(composition)
    issue = issue_request("kilo-cli-agent", "cross-cs", composition)
    result = site.invoke(
        cs_request(
            receiver_id="opencode-cli-agent",
            request_id="cross-cs",
            authorization_issue_request=issue,
        )
    )
    assert result.callsite_reason == "REAL_CALLSITE_TO_ADAPTER_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_opencode_callsite_cannot_become_kilo(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "opencode-cli-agent")
    assert composition.binding_controller.active_binding_count == 1
    assert composition.binding_controller.get_binding_for_receiver("kilo-cli-agent") is None
    site = live_callsite(composition)
    issue = issue_request("opencode-cli-agent", "cross-cs-2", composition)
    result = site.invoke(
        cs_request(
            receiver_id="kilo-cli-agent",
            request_id="cross-cs-2",
            authorization_issue_request=issue,
        )
    )
    assert result.callsite_reason == "REAL_CALLSITE_TO_ADAPTER_RECEIVER_MUTATION"
