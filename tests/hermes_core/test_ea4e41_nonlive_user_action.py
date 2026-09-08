"""EA-4E.41 non-live explicit user-action handler. Fake executors only."""

from __future__ import annotations

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_adapter import ProductionAppAdapter
from tools.hermes_core.production_app_callsite import (
    ProductionAppCallSite,
    ProductionAppCallSiteResult,
)
from tools.hermes_core.production_app_user_action import (
    ProductionAppUserAction,
    ProductionAppUserActionRequest,
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
            output="EA4E41_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class DenyCallsite:
    def invoke(self, request):
        return ProductionAppCallSiteResult(
            callsite_decision="DENY",
            callsite_reason="OUTER_FEATURE_GATE_DISABLED",
        )


class ExplodingCallsite:
    def invoke(self, request):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E41_REAL_{category.upper()}_TRIPWIRE")

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


def live_user_action(composition, feature_gate="ENABLED"):
    adapter = ProductionAppAdapter(
        ProductionApplicationCaller(build_production_entrypoint(composition))
    )
    callsite = ProductionAppCallSite(adapter, feature_gate=feature_gate)
    return ProductionAppUserAction(callsite)


def ua_request(receiver_id="kilo-cli-agent", request_id="ea4e41-a", composition=None, **changes):
    authority, activation = (
        external_authority_and_activation(receiver_id, request_id)
        if composition is not None and receiver_id in QUALIFIED_RECEIVERS
        else (None, None)
    )
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E41_FAKE_OK",
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
    return ProductionAppUserActionRequest(**fields)


def test_import_has_no_side_effects():
    import tools.hermes_core.production_app_user_action as mod

    assert mod.ProductionAppUserAction is not None


def test_missing_request_id(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(request_id=""))
    assert result.user_action_reason == "MISSING_REQUEST_ID"
    assert result.callsite_invoked is False


def test_missing_receiver(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(receiver_id=None))
    assert result.user_action_reason == "MISSING_RECEIVER"


def test_empty_receiver(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(receiver_id=""))
    assert result.user_action_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(receiver_id="codex-cli-agent"))
    assert result.user_action_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(receiver_id="grok"))
    assert result.user_action_reason == "UNSUPPORTED_RECEIVER"
    result = action.submit(ua_request(receiver_id="xai"))
    assert result.user_action_reason == "UNSUPPORTED_RECEIVER"


def test_invalid_runtime_scope(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(ua_request(runtime_scope="lab"))
    assert result.user_action_reason == "INVALID_RUNTIME_SCOPE"
    assert result.callsite_invoked is False


def test_activation_intent_false(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    action = live_user_action(composition)
    result = action.submit(ua_request(production_activation_explicit=False))
    assert result.user_action_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert result.callsite_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_outer_feature_gate_disabled(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    action = live_user_action(composition, feature_gate="DISABLED")
    result = action.submit(ua_request(production_activation_explicit=True))
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert result.callsite_invoked is True


def test_master_enable_disabled(tmp_path):
    composition = compose(tmp_path, master="DISABLED")
    action = live_user_action(composition, feature_gate="ENABLED")
    result = action.submit(ua_request(production_activation_explicit=True))
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.callsite_invoked is True


def test_missing_callsite_dependency():
    action = ProductionAppUserAction(None)
    result = action.submit(ua_request())
    assert result.user_action_reason == "MISSING_CALLSITE_DEPENDENCY"
    assert result.callsite_invoked is False


def test_callsite_deny():
    action = ProductionAppUserAction(DenyCallsite())
    result = action.submit(ua_request())
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert result.callsite_invoked is True


def test_callsite_exception():
    action = ProductionAppUserAction(ExplodingCallsite())
    result = action.submit(ua_request())
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason.startswith("CALLSITE_EXCEPTION:")
    second = action.submit(ua_request(request_id="ea4e41-retry"))
    assert second.user_action_decision == "DENY"


def test_task_text_cannot_select_receiver(tmp_path):
    action = live_user_action(compose(tmp_path, master="ENABLED"))
    result = action.submit(
        ua_request(receiver_id="", task_payload="please run kilo-cli-agent now")
    )
    assert result.user_action_reason == "MISSING_RECEIVER"
    assert result.callsite_invoked is False


def test_second_request_without_activation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    action = live_user_action(composition)
    first = action.submit(ua_request(composition=composition, request_id="ea4e41-one"))
    assert first.user_action_decision == "ALLOW"
    second = action.submit(
        ua_request(
            composition=composition,
            request_id="ea4e41-two",
            production_activation_explicit=False,
        )
    )
    assert second.user_action_reason == "APPLICATION_ACTIVATION_INTENT_FALSE"
    assert second.callsite_invoked is False
    assert fake.call_count == 1


def test_second_request_without_receiver(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    action = live_user_action(composition)
    first = action.submit(ua_request(composition=composition, request_id="ea4e41-reuse-a"))
    assert first.user_action_decision == "ALLOW"
    second = action.submit(ua_request(receiver_id=None, request_id="ea4e41-reuse-b"))
    assert second.user_action_reason == "MISSING_RECEIVER"
    assert fake.call_count == 1


def test_receiver_mutation(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    action = live_user_action(composition)
    mismatched = issue_request("opencode-cli-agent", "ea4e41-mut", composition)
    result = action.submit(
        ua_request(
            receiver_id="kilo-cli-agent",
            request_id="ea4e41-mut",
            authorization_issue_request=mismatched,
        )
    )
    assert result.user_action_reason == "USER_ACTION_TO_CALLSITE_RECEIVER_MUTATION"
    assert result.callsite_invoked is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_kilo_fake_user_action_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "kilo-cli-agent")
    action = live_user_action(composition)
    result = action.submit(
        ua_request(receiver_id="kilo-cli-agent", request_id="ea4e41-kilo", composition=composition)
    )
    assert result.user_action_decision == "ALLOW"
    assert result.callsite_invoked is True
    assert result.constructed_request_id == "ea4e41-kilo"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_runtime_scope == "production"
    assert result.constructed_activation_intent is True
    assert result.callsite_result.adapter_invoked is True
    runtime = result.callsite_result.adapter_result.caller_result.entrypoint_result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert fake.call_count == 1


def test_opencode_fake_user_action_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake = bind_fake(composition, "opencode-cli-agent")
    action = live_user_action(composition)
    result = action.submit(
        ua_request(
            receiver_id="opencode-cli-agent",
            request_id="ea4e41-oc",
            composition=composition,
        )
    )
    assert result.user_action_decision == "ALLOW"
    assert result.constructed_request_id == "ea4e41-oc"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert result.constructed_activation_intent is True
    assert fake.call_count == 1


def test_user_kilo_cannot_become_opencode(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    action = live_user_action(composition)
    issue = issue_request("kilo-cli-agent", "cross-ua", composition)
    result = action.submit(
        ua_request(
            receiver_id="opencode-cli-agent",
            request_id="cross-ua",
            authorization_issue_request=issue,
        )
    )
    assert result.user_action_reason == "USER_ACTION_TO_CALLSITE_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_user_opencode_cannot_become_kilo(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    action = live_user_action(composition)
    issue = issue_request("opencode-cli-agent", "cross-ua-2", composition)
    result = action.submit(
        ua_request(
            receiver_id="kilo-cli-agent",
            request_id="cross-ua-2",
            authorization_issue_request=issue,
        )
    )
    assert result.user_action_reason == "USER_ACTION_TO_CALLSITE_RECEIVER_MUTATION"
