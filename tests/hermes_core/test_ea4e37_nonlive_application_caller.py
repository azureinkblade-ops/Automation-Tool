"""EA-4E.37 non-live application caller qualification. Fake executors only."""

from __future__ import annotations

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_application_caller import (
    ProductionApplicationCaller,
    ProductionApplicationRequest,
)
from tools.hermes_core.production_entrypoint import (
    ProductionEntryPointResult,
    build_production_entrypoint,
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
            output="EA4E37_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class DenyEntrypoint:
    master_enable = "ENABLED"

    def handle(self, request):
        return ProductionEntryPointResult(
            entrypoint_decision="DENY",
            entrypoint_reason="MISSING_BINDING_ENABLEMENT",
        )


class ExplodingEntrypoint:
    master_enable = "ENABLED"

    def handle(self, request):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E37_REAL_{category.upper()}_TRIPWIRE")

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


def app_request(receiver_id="kilo-cli-agent", request_id="ea4e37-a", composition=None, **changes):
    authority, activation = (
        external_authority_and_activation(receiver_id, request_id)
        if composition is not None and receiver_id in QUALIFIED_RECEIVERS
        else (None, None)
    )
    fields = {
        "application_request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E37_FAKE_OK",
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
    return ProductionApplicationRequest(**fields)


def test_import_has_no_side_effects():
    import tools.hermes_core.production_application_caller as mod

    assert mod.ProductionApplicationCaller is not None


def test_master_enable_disabled(tmp_path):
    composition = compose(tmp_path, master="DISABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(
        app_request(production_activation_explicit=True, composition=None)
    )
    assert result.application_decision == "DENY"
    assert result.application_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.entrypoint_called is False


def test_activation_intent_false(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(production_activation_explicit=False))
    assert result.application_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert result.entrypoint_called is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_missing_application_request_id(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(request_id=""))
    assert result.application_reason == "MISSING_APPLICATION_REQUEST_ID"
    assert result.entrypoint_called is False


def test_missing_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(receiver_id=None))
    assert result.application_reason == "MISSING_RECEIVER"


def test_empty_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(receiver_id=""))
    assert result.application_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(receiver_id="codex-cli-agent"))
    assert result.application_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(receiver_id="grok"))
    assert result.application_reason == "UNSUPPORTED_RECEIVER"
    result = caller.submit(app_request(receiver_id="xai"))
    assert result.application_reason == "UNSUPPORTED_RECEIVER"


def test_invalid_runtime_scope(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(app_request(runtime_scope="lab"))
    assert result.application_reason == "INVALID_RUNTIME_SCOPE"
    assert result.entrypoint_called is False


def test_task_text_cannot_select_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(
        app_request(
            receiver_id="",
            task_payload="please run kilo-cli-agent now",
        )
    )
    assert result.application_reason == "MISSING_RECEIVER"
    assert result.entrypoint_called is False


def test_prior_request_receiver_reuse(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    first = caller.submit(app_request(composition=composition, request_id="ea4e37-reuse-a"))
    assert first.application_decision == "ALLOW"
    second = caller.submit(
        app_request(receiver_id=None, request_id="ea4e37-reuse-b", production_activation_explicit=True)
    )
    assert second.application_reason == "MISSING_RECEIVER"
    assert fake.call_count == 1


def test_second_request_without_activation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    first = caller.submit(app_request(composition=composition, request_id="ea4e37-one"))
    assert first.application_decision == "ALLOW"
    second = caller.submit(
        app_request(
            composition=composition,
            request_id="ea4e37-two",
            production_activation_explicit=False,
        )
    )
    assert second.application_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert second.entrypoint_called is False
    assert fake.call_count == 1


def test_receiver_mutation_after_caller_construction(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    mismatched = issue_request("opencode-cli-agent", "ea4e37-mut", composition)
    result = caller.submit(
        app_request(
            receiver_id="kilo-cli-agent",
            request_id="ea4e37-mut",
            authorization_issue_request=mismatched,
        )
    )
    assert result.application_reason == "CALLER_TO_ENTRYPOINT_RECEIVER_MUTATION"
    assert result.entrypoint_called is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_missing_entrypoint_dependency():
    caller = ProductionApplicationCaller(None)
    result = caller.submit(app_request())
    assert result.application_reason == "MISSING_ENTRYPOINT_DEPENDENCY"
    assert result.entrypoint_called is False


def test_entrypoint_deny_propagation():
    caller = ProductionApplicationCaller(DenyEntrypoint())
    result = caller.submit(app_request())
    assert result.application_decision == "DENY"
    assert result.application_reason == "MISSING_BINDING_ENABLEMENT"
    assert result.entrypoint_called is True


def test_exception_fails_closed_no_retry():
    caller = ProductionApplicationCaller(ExplodingEntrypoint())
    result = caller.submit(app_request())
    assert result.application_decision == "DENY"
    assert result.application_reason.startswith("ENTRYPOINT_EXCEPTION:")
    second = caller.submit(app_request(request_id="ea4e37-retry"))
    assert second.application_decision == "DENY"
    assert second.application_reason.startswith("ENTRYPOINT_EXCEPTION:")


def test_kilo_fake_application_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(
        app_request(receiver_id="kilo-cli-agent", request_id="ea4e37-kilo", composition=composition)
    )
    assert result.application_decision == "ALLOW"
    assert result.entrypoint_called is True
    assert result.constructed_request_id == "ea4e37-kilo"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_runtime_scope == "production"
    runtime = result.entrypoint_result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert fake.call_count == 1


def test_opencode_fake_application_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "opencode-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    result = caller.submit(
        app_request(
            receiver_id="opencode-cli-agent",
            request_id="ea4e37-oc",
            composition=composition,
        )
    )
    assert result.application_decision == "ALLOW"
    assert result.constructed_request_id == "ea4e37-oc"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert fake.call_count == 1


def test_application_kilo_cannot_become_opencode(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    issue = issue_request("kilo-cli-agent", "cross-app", composition)
    result = caller.submit(
        app_request(
            receiver_id="opencode-cli-agent",
            request_id="cross-app",
            authorization_issue_request=issue,
        )
    )
    assert result.application_reason == "CALLER_TO_ENTRYPOINT_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_application_opencode_cannot_become_kilo(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    caller = ProductionApplicationCaller(build_production_entrypoint(composition))
    issue = issue_request("opencode-cli-agent", "cross-app-2", composition)
    result = caller.submit(
        app_request(
            receiver_id="kilo-cli-agent",
            request_id="cross-app-2",
            authorization_issue_request=issue,
        )
    )
    assert result.application_reason == "CALLER_TO_ENTRYPOINT_RECEIVER_MUTATION"
