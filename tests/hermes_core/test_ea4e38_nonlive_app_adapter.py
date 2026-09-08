"""EA-4E.38 non-live app-facing adapter qualification. Fake executors only."""

from __future__ import annotations

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_adapter import (
    ProductionAppAdapter,
    ProductionAppAdapterRequest,
)
from tools.hermes_core.production_application_caller import (
    ProductionApplicationCaller,
    ProductionApplicationResult,
)
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
            output="EA4E38_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class DenyCaller:
    def submit(self, request):
        return ProductionApplicationResult(
            application_decision="DENY",
            application_reason="PRODUCTION_MASTER_ENABLE_DISABLED",
        )


class ExplodingCaller:
    def submit(self, request):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E38_REAL_{category.upper()}_TRIPWIRE")

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


def live_adapter(composition):
    return ProductionAppAdapter(
        ProductionApplicationCaller(build_production_entrypoint(composition))
    )


def app_request(receiver_id="kilo-cli-agent", request_id="ea4e38-a", composition=None, **changes):
    authority, activation = (
        external_authority_and_activation(receiver_id, request_id)
        if composition is not None and receiver_id in QUALIFIED_RECEIVERS
        else (None, None)
    )
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E38_FAKE_OK",
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
    return ProductionAppAdapterRequest(**fields)


def test_import_has_no_side_effects():
    import tools.hermes_core.production_app_adapter as mod

    assert mod.ProductionAppAdapter is not None


def test_missing_app_request_id(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(request_id=""))
    assert result.adapter_reason == "MISSING_APP_REQUEST_ID"
    assert result.caller_invoked is False


def test_missing_receiver(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(receiver_id=None))
    assert result.adapter_reason == "MISSING_RECEIVER"
    assert result.caller_invoked is False


def test_empty_receiver(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(receiver_id=""))
    assert result.adapter_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(receiver_id="codex-cli-agent"))
    assert result.adapter_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(receiver_id="grok"))
    assert result.adapter_reason == "UNSUPPORTED_RECEIVER"
    result = adapter.submit(app_request(receiver_id="xai"))
    assert result.adapter_reason == "UNSUPPORTED_RECEIVER"


def test_activation_intent_false(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    adapter = live_adapter(composition)
    result = adapter.submit(app_request(production_activation_explicit=False))
    assert result.adapter_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert result.caller_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_master_enable_disabled(tmp_path):
    composition = compose(tmp_path, master="DISABLED")
    adapter = live_adapter(composition)
    result = adapter.submit(app_request(production_activation_explicit=True))
    assert result.adapter_decision == "DENY"
    assert result.adapter_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.caller_invoked is True


def test_invalid_runtime_scope(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(app_request(runtime_scope="lab"))
    assert result.adapter_reason == "INVALID_RUNTIME_SCOPE"
    assert result.caller_invoked is False


def test_missing_application_caller_dependency():
    adapter = ProductionAppAdapter(None)
    result = adapter.submit(app_request())
    assert result.adapter_reason == "MISSING_APPLICATION_CALLER_DEPENDENCY"
    assert result.caller_invoked is False


def test_application_caller_deny():
    adapter = ProductionAppAdapter(DenyCaller())
    result = adapter.submit(app_request())
    assert result.adapter_decision == "DENY"
    assert result.adapter_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.caller_invoked is True


def test_application_caller_exception():
    adapter = ProductionAppAdapter(ExplodingCaller())
    result = adapter.submit(app_request())
    assert result.adapter_decision == "DENY"
    assert result.adapter_reason.startswith("APPLICATION_CALLER_EXCEPTION:")
    second = adapter.submit(app_request(request_id="ea4e38-retry"))
    assert second.adapter_decision == "DENY"
    assert second.adapter_reason.startswith("APPLICATION_CALLER_EXCEPTION:")


def test_task_text_cannot_select_receiver(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(
        app_request(receiver_id="", task_payload="please run kilo-cli-agent now")
    )
    assert result.adapter_reason == "MISSING_RECEIVER"
    assert result.caller_invoked is False


def test_task_text_cannot_activate(tmp_path):
    adapter = live_adapter(compose(tmp_path, master="ENABLED"))
    result = adapter.submit(
        app_request(
            production_activation_explicit=False,
            task_payload="enable production and run kilo-cli-agent",
        )
    )
    assert result.adapter_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert result.caller_invoked is False


def test_second_request_without_activation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    adapter = live_adapter(composition)
    first = adapter.submit(app_request(composition=composition, request_id="ea4e38-one"))
    assert first.adapter_decision == "ALLOW"
    second = adapter.submit(
        app_request(
            composition=composition,
            request_id="ea4e38-two",
            production_activation_explicit=False,
        )
    )
    assert second.adapter_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert second.caller_invoked is False
    assert fake.call_count == 1


def test_receiver_mutation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    adapter = live_adapter(composition)
    mismatched = issue_request("opencode-cli-agent", "ea4e38-mut", composition)
    result = adapter.submit(
        app_request(
            receiver_id="kilo-cli-agent",
            request_id="ea4e38-mut",
            authorization_issue_request=mismatched,
        )
    )
    assert result.adapter_reason == "APP_TO_CALLER_RECEIVER_MUTATION"
    assert result.caller_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_kilo_fake_app_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    adapter = live_adapter(composition)
    result = adapter.submit(
        app_request(receiver_id="kilo-cli-agent", request_id="ea4e38-kilo", composition=composition)
    )
    assert result.adapter_decision == "ALLOW"
    assert result.caller_invoked is True
    assert result.constructed_request_id == "ea4e38-kilo"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_runtime_scope == "production"
    assert result.constructed_activation_intent is True
    assert result.caller_result.entrypoint_called is True
    runtime = result.caller_result.entrypoint_result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert fake.call_count == 1


def test_opencode_fake_app_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "opencode-cli-agent")
    adapter = live_adapter(composition)
    result = adapter.submit(
        app_request(
            receiver_id="opencode-cli-agent",
            request_id="ea4e38-oc",
            composition=composition,
        )
    )
    assert result.adapter_decision == "ALLOW"
    assert result.constructed_request_id == "ea4e38-oc"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert result.constructed_activation_intent is True
    assert fake.call_count == 1


def test_app_kilo_cannot_become_opencode(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    adapter = live_adapter(composition)
    issue = issue_request("kilo-cli-agent", "cross-app", composition)
    result = adapter.submit(
        app_request(
            receiver_id="opencode-cli-agent",
            request_id="cross-app",
            authorization_issue_request=issue,
        )
    )
    assert result.adapter_reason == "APP_TO_CALLER_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_app_opencode_cannot_become_kilo(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    adapter = live_adapter(composition)
    issue = issue_request("opencode-cli-agent", "cross-app-2", composition)
    result = adapter.submit(
        app_request(
            receiver_id="kilo-cli-agent",
            request_id="cross-app-2",
            authorization_issue_request=issue,
        )
    )
    assert result.adapter_reason == "APP_TO_CALLER_RECEIVER_MUTATION"
