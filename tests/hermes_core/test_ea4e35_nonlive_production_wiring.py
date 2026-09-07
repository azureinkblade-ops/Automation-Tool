"""EA-4E.35 non-live production wiring fail-closed matrix. Fake executors only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tools.hermes_core.governed_production_caller import GovernedProductionCallerRequest
from tools.hermes_core.governed_production_runtime import GovernedProductionRuntimeRequest
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController, PINNED_KILO_PATH
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import (
    OpenCodeLiveProcess,
    OpenCodeReceiverAdapter,
    PINNED_OPENCODE_PATH,
)
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_activation import build_production_activation
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
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    DispatchAuthorityScope,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_wiring import (
    ProductionWiringConfig,
    ProductionWiringError,
    assemble_production_composition,
    classify_receiver,
    initialize_production_auth_store,
    open_production_auth_store,
    register_qualified_real_executors,
    verify_frozen_executor_paths,
)
from tools.hermes_core.receiver_router import RoutingRequest, compute_ea4e6_router_contract_id


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
            output="EA4E35_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E35_REAL_{category.upper()}_TRIPWIRE")

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
    store = tmp_path / "invocation-authorization.sqlite3"
    anchor = tmp_path / "invocation-authorization.anchor.json"
    return ProductionWiringConfig(
        auth_store_path=store,
        auth_anchor_path=anchor,
        **changes,
    )


def enabled_config(tmp_path) -> ProductionWiringConfig:
    return wiring_config(
        tmp_path,
        master_enable="ENABLED",
        production_activation_default="ENABLED",
    )


def compose(tmp_path, config=None, *, initialize=True, fake_registry=True):
    cfg = config or wiring_config(tmp_path)
    if initialize:
        initialize_production_auth_store(cfg)
    clock = ClockCollaborator(now=NOW)
    registry = ExecutorRegistry()
    if fake_registry:
        for receiver_id in ("kilo-cli-agent", "opencode-cli-agent"):
            registry.register(receiver_id, FakeExecutor(receiver_id))
    return assemble_production_composition(
        cfg,
        clock=clock,
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
    handle = composition.binding_controller.bind(
        enablement, ExecutorRegistry(), executor_factory=lambda: fake
    )
    return fake, handle


def caller_request(receiver_id="kilo-cli-agent", request_id="ea4e35-request-1", handle=None, **runtime_changes):
    receiver = QUALIFIED_RECEIVERS.get(receiver_id, QUALIFIED_RECEIVERS["kilo-cli-agent"])
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "router_contract_id": compute_ea4e6_router_contract_id(),
        "transport_contract_id": receiver["transport_contract_id"],
        "model_binding_id": receiver["model_binding_id"],
    }
    fields.update(runtime_changes)
    runtime_request = GovernedProductionRuntimeRequest(**fields)
    issue_request = ProductionInvocationAuthorizationIssueRequest(
        issue_request_id=f"issue-{request_id}",
        execution_request_id=request_id,
        receiver_id=receiver_id,
        binding_id=handle.binding_id if handle else f"binding-{receiver_id}",
        enablement_id=handle.enablement_id if handle else f"enablement-{receiver_id}",
        nonce=f"nonce-{request_id}",
    )
    return GovernedProductionCallerRequest(runtime_request, issue_request)


def test_missing_receiver():
    assert classify_receiver("") == "MISSING_RECEIVER"
    assert classify_receiver(None) == "MISSING_RECEIVER"


def test_unsupported_receiver_and_grok():
    assert classify_receiver("codex-cli-agent") == "UNSUPPORTED_RECEIVER"
    assert classify_receiver("grok") == "UNSUPPORTED_RECEIVER"
    assert classify_receiver("grok-cli") == "UNSUPPORTED_RECEIVER"
    assert classify_receiver("xai") == "UNSUPPORTED_RECEIVER"


def test_production_activation_disabled_default(tmp_path):
    composition = compose(tmp_path)
    result = composition.invoke(caller_request())
    assert result.caller_decision == "DENY"
    assert result.caller_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"


def test_production_activation_disabled_when_master_enabled(tmp_path):
    composition = compose(
        tmp_path,
        wiring_config(tmp_path, master_enable="ENABLED", production_activation_default="DISABLED"),
    )
    result = composition.invoke(caller_request())
    assert result.caller_reason == "PRODUCTION_ACTIVATION_DISABLED"


def test_auth_store_missing(tmp_path):
    with pytest.raises(ProductionWiringError) as exc:
        compose(tmp_path, initialize=False)
    assert exc.value.reason == "AUTH_STORE_MISSING"


def test_anchor_missing_or_invalid(tmp_path):
    cfg = wiring_config(tmp_path)
    initialize_production_auth_store(cfg)
    Path(cfg.auth_anchor_path).unlink()
    with pytest.raises(ProductionWiringError) as exc:
        open_production_auth_store(cfg)
    assert exc.value.reason == "ANCHOR_MISSING_OR_INVALID"


def test_authority_missing(tmp_path):
    composition = compose(tmp_path)
    route = composition.router.route(
        RoutingRequest(receiver_id="kilo-cli-agent", execution_authority_present=False)
    )
    result = composition.authority_validator.validate(None, route)
    assert result.authority_valid is False
    assert result.reason == "EXECUTION_AUTHORITY_MISSING"


def test_authority_denied(tmp_path):
    composition = compose(tmp_path)
    route = composition.router.route(
        RoutingRequest(receiver_id="kilo-cli-agent", execution_authority_present=True)
    )
    authority = DispatchAuthority(
        authority_id="denied-authority",
        artifact_version="1",
        artifact_hash="0" * 64,
        receiver_id="kilo-cli-agent",
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        router_contract_id=compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(
            operation="receiver-dispatch",
            receiver_id="kilo-cli-agent",
            attempt_limit=1,
        ),
        delegation_class="governed",
        decision="DENIED",
        issued_at=NOW,
        expires_at="2026-01-01T00:05:00Z",
        nonce="denied-nonce",
    )
    result = composition.authority_validator.validate(authority, route)
    assert result.authority_valid is False
    assert result.reason == "EXECUTION_AUTHORITY_DENIED"


def test_receiver_binding_mismatch_via_invoke(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    _, kilo_handle = bind_fake(composition, "kilo-cli-agent")
    request = caller_request(
        receiver_id="opencode-cli-agent",
        request_id="ea4e35-mismatch",
        handle=kilo_handle,
    )
    result = composition.invoke(request)
    assert result.caller_decision == "DENY"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_transport_contract_mismatch(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    _, handle = bind_fake(composition)
    request = caller_request(handle=handle, transport_contract_id="0" * 64)
    result = composition.invoke(request)
    assert result.caller_decision == "DENY"
    assert "TRANSPORT_CONTRACT_MISMATCH" in result.caller_reason or "TRANSPORT" in result.caller_reason
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_model_binding_mismatch(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    _, handle = bind_fake(composition)
    request = caller_request(handle=handle, model_binding_id="0" * 64)
    result = composition.invoke(request)
    assert result.caller_decision == "DENY"
    assert "MODEL_BINDING_MISMATCH" in result.caller_reason or "MODEL" in result.caller_reason
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_executable_binding_mismatch():
    cfg = ProductionWiringConfig(kilo_executable_path=r"C:\not\the\frozen\kilo.exe")
    with pytest.raises(ProductionWiringError) as exc:
        verify_frozen_executor_paths(cfg)
    assert exc.value.reason == "EXECUTABLE_BINDING_MISMATCH"


def test_invocation_auth_missing(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    request = caller_request()
    result = composition.invoke(replace(request, authorization_issue_request=None))
    assert result.caller_decision == "DENY"
    assert result.caller_reason == "AUTHORIZATION_ISSUE_REQUEST_REQUIRED"


def test_invocation_auth_denied_receiver_mismatch(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    _, handle = bind_fake(composition, "kilo-cli-agent")
    request = caller_request(receiver_id="kilo-cli-agent", handle=handle)
    other = replace(
        request.authorization_issue_request,
        receiver_id="opencode-cli-agent",
    )
    result = composition.invoke(replace(request, authorization_issue_request=other))
    assert result.caller_decision == "DENY"
    assert result.caller_reason == "RECEIVER_ID_MISMATCH"


def test_consumed_auth_replay(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    fake, handle = bind_fake(composition)
    request = caller_request(handle=handle, request_id="ea4e35-replay-a")
    resolution = composition.resolver.resolve_governed_executor("kilo-cli-agent")
    issued = composition.issuer.issue(request.authorization_issue_request, resolution)
    assert issued.policy_decision == "ALLOW"
    runtime_request = replace(
        request.runtime_request,
        invocation_authorization=issued.authorization,
    )
    first = composition.runtime.execute(runtime_request)
    assert first.ea4e26_disposition == "PASS"
    assert fake.call_count == 1
    second = composition.runtime.execute(runtime_request)
    assert second.invocation_claim_decision == "DENY"
    assert "CONSUMED" in second.invocation_claim_reason or "CONSUMED" in second.reason
    assert fake.call_count == 1


def test_activation_validator_disabled(tmp_path):
    composition = compose(tmp_path)
    receiver = QUALIFIED_RECEIVERS["kilo-cli-agent"]
    activation = build_production_activation(
        receiver_id="kilo-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=receiver["transport_contract_id"],
        model_binding_id=receiver["model_binding_id"],
        activation_mode="DISABLED",
        execution_scope="single-shot",
        delegation_class="governed",
    )
    result = composition.activation_validator.validate(
        activation, receiver_id="kilo-cli-agent"
    )
    assert result.reason == "PRODUCTION_ACTIVATION_DISABLED"


def test_no_default_receiver_and_no_task_text_heuristic():
    cfg = ProductionWiringConfig()
    assert cfg.default_receiver == "NONE"
    assert cfg.receiver_id is None
    assert cfg.master_enable == "DISABLED"


def test_frozen_paths_match_qualified_binaries():
    cfg = ProductionWiringConfig()
    assert cfg.kilo_executable_path == PINNED_KILO_PATH
    assert cfg.opencode_executable_path == PINNED_OPENCODE_PATH
    verify_frozen_executor_paths(cfg)


def test_real_executors_register_without_execute(tmp_path):
    cfg = wiring_config(tmp_path)
    initialize_production_auth_store(cfg)
    registry = ExecutorRegistry()
    register_qualified_real_executors(registry, config=cfg)
    assert registry.has_executor("kilo-cli-agent")
    assert registry.has_executor("opencode-cli-agent")
    assert registry.resolve("kilo-cli-agent").executor_id == "RealKiloProductionExecutor"
    assert registry.resolve("opencode-cli-agent").executor_id == "RealOpenCodeProductionExecutor"


def test_grok_invoke_never_executes(tmp_path):
    composition = compose(tmp_path, enabled_config(tmp_path))
    result = composition.invoke(caller_request(receiver_id="grok"))
    assert result.caller_reason == "UNSUPPORTED_RECEIVER"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_assemble_does_not_use_automation_state_db(tmp_path):
    cfg = wiring_config(tmp_path)
    assert Path(cfg.auth_store_path).name != "automation_state.db"
    with pytest.raises(ProductionWiringError) as exc:
        open_production_auth_store(
            replace(cfg, auth_store_path=tmp_path / "automation_state.db")
        )
    assert exc.value.reason == "AUTOMATION_STATE_DB_FORBIDDEN"
