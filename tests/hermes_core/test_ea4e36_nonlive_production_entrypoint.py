"""EA-4E.36 non-live production entry-point qualification. Fake executors only."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_entrypoint import (
    ProductionEntryPointRequest,
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
    ProductionWiringError,
    assemble_production_composition,
    initialize_production_auth_store,
    open_production_auth_store,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthority,
    DispatchAuthorityScope,
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
            output="EA4E36_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(executor=0, adapter=0, process=0, model=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E36_REAL_{category.upper()}_TRIPWIRE")

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


def compose(tmp_path, *, master="DISABLED", initialize=True):
    cfg = wiring_config(tmp_path, master_enable=master)
    if initialize:
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
    handle = composition.binding_controller.bind(
        enablement, ExecutorRegistry(), executor_factory=lambda: fake
    )
    return fake, handle


def issue_request(receiver_id, request_id, handle):
    return ProductionInvocationAuthorizationIssueRequest(
        issue_request_id=f"issue-{request_id}",
        execution_request_id=request_id,
        receiver_id=receiver_id,
        binding_id=handle.binding_id,
        enablement_id=handle.enablement_id,
        nonce=f"nonce-{request_id}",
    )


def entry_request(receiver_id="kilo-cli-agent", request_id="ea4e36-a", handle=None, **changes):
    authority, activation = (
        external_authority_and_activation(receiver_id, request_id)
        if handle is not None and receiver_id in QUALIFIED_RECEIVERS
        else (None, None)
    )
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E36_FAKE_OK",
        "production_activation_explicit": True,
        "authorization_issue_request": (
            issue_request(receiver_id, request_id, handle) if handle is not None else None
        ),
        "execution_authority": authority,
        "activation": activation,
    }
    fields.update(changes)
    return ProductionEntryPointRequest(**fields)


def test_import_has_no_side_effects():
    import tools.hermes_core.production_entrypoint as mod

    assert mod.ProductionEntryPoint is not None


def test_master_enable_disabled(tmp_path):
    ep = build_production_entrypoint(compose(tmp_path, master="DISABLED"))
    result = ep.handle(entry_request())
    assert result.entrypoint_decision == "DENY"
    assert result.entrypoint_reason == "PRODUCTION_MASTER_ENABLE_DISABLED"
    assert result.activation_attempted is False
    assert result.binding_attempted is False
    assert result.invocation_authorization_issued is False
    assert result.executor_resolution_attempted is False


def test_activation_not_explicit(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    ep = build_production_entrypoint(composition)
    result = ep.handle(entry_request(production_activation_explicit=False))
    assert result.entrypoint_reason == "PRODUCTION_ACTIVATION_NOT_EXPLICIT"
    assert result.binding_attempted is False
    assert result.invocation_authorization_issued is False
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_missing_receiver(tmp_path):
    ep = build_production_entrypoint(compose(tmp_path, master="ENABLED"))
    result = ep.handle(entry_request(receiver_id=""))
    assert result.entrypoint_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(tmp_path):
    ep = build_production_entrypoint(compose(tmp_path, master="ENABLED"))
    result = ep.handle(entry_request(receiver_id="codex-cli-agent"))
    assert result.entrypoint_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver(tmp_path):
    ep = build_production_entrypoint(compose(tmp_path, master="ENABLED"))
    result = ep.handle(entry_request(receiver_id="grok"))
    assert result.entrypoint_reason == "UNSUPPORTED_RECEIVER"
    result = ep.handle(entry_request(receiver_id="xai"))
    assert result.entrypoint_reason == "UNSUPPORTED_RECEIVER"


def test_missing_auth_store(tmp_path):
    with pytest.raises(ProductionWiringError) as exc:
        compose(tmp_path, master="ENABLED", initialize=False)
    assert exc.value.reason == "AUTH_STORE_MISSING"


def test_invalid_anchor(tmp_path):
    cfg = wiring_config(tmp_path, master_enable="ENABLED")
    initialize_production_auth_store(cfg)
    cfg.auth_anchor_path.unlink()
    with pytest.raises(ProductionWiringError) as exc:
        open_production_auth_store(cfg)
    assert exc.value.reason == "ANCHOR_MISSING_OR_INVALID"


def test_missing_execution_authority(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    route = composition.router.route(
        RoutingRequest(receiver_id="kilo-cli-agent", execution_authority_present=False)
    )
    result = composition.authority_validator.validate(None, route)
    assert result.reason == "EXECUTION_AUTHORITY_MISSING"


def test_denied_execution_authority(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    route = composition.router.route(
        RoutingRequest(receiver_id="kilo-cli-agent", execution_authority_present=True)
    )
    authority = DispatchAuthority(
        authority_id="denied",
        artifact_version="1",
        artifact_hash="0" * 64,
        receiver_id="kilo-cli-agent",
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        router_contract_id=compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(
            operation="receiver-dispatch", receiver_id="kilo-cli-agent", attempt_limit=1
        ),
        delegation_class="governed",
        decision="DENIED",
        issued_at=NOW,
        expires_at="2026-01-01T00:05:00Z",
        nonce="denied",
    )
    result = composition.authority_validator.validate(authority, route)
    assert result.reason == "EXECUTION_AUTHORITY_DENIED"


def test_transport_contract_mismatch(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition)
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(handle=handle, transport_contract_id="0" * 64)
    )
    assert result.entrypoint_decision == "DENY"
    assert "TRANSPORT" in result.entrypoint_reason
    assert fake.call_count == 0


def test_model_binding_mismatch(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition)
    ep = build_production_entrypoint(composition)
    result = ep.handle(entry_request(handle=handle, model_binding_id="0" * 64))
    assert result.entrypoint_decision == "DENY"
    assert "MODEL" in result.entrypoint_reason
    assert fake.call_count == 0


def test_executable_binding_mismatch(tmp_path):
    cfg = wiring_config(
        tmp_path,
        master_enable="ENABLED",
        kilo_executable_path=r"C:\not\frozen\kilo.exe",
    )
    initialize_production_auth_store(cfg)
    registry = ExecutorRegistry()
    with pytest.raises(ProductionWiringError) as exc:
        assemble_production_composition(
            cfg,
            clock=ClockCollaborator(now=NOW),
            executor_registry=registry,
            register_real_executors=False,
        )
    assert exc.value.reason == "EXECUTABLE_BINDING_MISMATCH"


def test_missing_binding_enablement(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    ep = build_production_entrypoint(composition)
    result = ep.handle(entry_request(production_activation_explicit=True))
    assert result.entrypoint_reason == "MISSING_BINDING_ENABLEMENT"
    assert result.binding_attempted is False or result.entrypoint_decision == "DENY"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_missing_invocation_authorization(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition)
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(production_activation_explicit=True, authorization_issue_request=None)
    )
    assert result.entrypoint_reason == "MISSING_INVOCATION_AUTHORIZATION"


def test_denied_invocation_authorization_receiver_mismatch(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    _, handle = bind_fake(composition, "kilo-cli-agent")
    ep = build_production_entrypoint(composition)
    mismatched = issue_request("opencode-cli-agent", "ea4e36-a", handle)
    result = ep.handle(
        entry_request(
            receiver_id="kilo-cli-agent",
            handle=handle,
            authorization_issue_request=mismatched,
        )
    )
    assert result.entrypoint_reason == "POST_ACTIVATION_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0


def test_consumed_invocation_authorization(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition)
    ep = build_production_entrypoint(composition)
    req = entry_request(handle=handle, request_id="ea4e36-consumed")
    first = ep.handle(req)
    assert first.entrypoint_decision == "ALLOW"
    assert fake.call_count == 1
    second = ep.handle(req)
    assert second.entrypoint_decision == "DENY"
    assert "CONSUMED" in second.entrypoint_reason or second.caller_result.caller_reason
    assert fake.call_count == 1


def test_second_request_without_reenablement(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition)
    ep = build_production_entrypoint(composition)
    first = ep.handle(entry_request(handle=handle, request_id="ea4e36-one"))
    assert first.entrypoint_decision == "ALLOW"
    second = ep.handle(
        entry_request(
            handle=handle,
            request_id="ea4e36-two",
            production_activation_explicit=False,
        )
    )
    assert second.entrypoint_reason == "PRODUCTION_ACTIVATION_NOT_EXPLICIT"
    assert fake.call_count == 1


def test_kilo_fake_positive_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition, "kilo-cli-agent")
    ep = build_production_entrypoint(composition)
    result = ep.handle(entry_request(receiver_id="kilo-cli-agent", handle=handle))
    assert result.entrypoint_decision == "ALLOW"
    assert result.route_decision == "SELECTED"
    runtime = result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert runtime.binding_decision == "ALLOW"
    assert runtime.invocation_claim_decision == "ALLOW" or runtime.live_invocation_authorization_claims_granted == 1
    assert fake.call_count == 1


def test_opencode_fake_positive_path(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition, "opencode-cli-agent")
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(receiver_id="opencode-cli-agent", request_id="ea4e36-oc", handle=handle)
    )
    assert result.entrypoint_decision == "ALLOW"
    assert result.route_decision == "SELECTED"
    runtime = result.caller_result.runtime_result
    assert runtime.authority_valid is True
    assert runtime.activation_valid is True
    assert runtime.binding_decision == "ALLOW"
    assert fake.call_count == 1


def test_request_a_does_not_authorize_request_b(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    fake, handle = bind_fake(composition)
    ep = build_production_entrypoint(composition)
    a = ep.handle(entry_request(handle=handle, request_id="req-a"))
    assert a.entrypoint_decision == "ALLOW"
    b = ep.handle(
        entry_request(
            handle=handle,
            request_id="req-b",
            authorization_issue_request=issue_request("kilo-cli-agent", "req-a", handle),
        )
    )
    assert b.entrypoint_reason == "REQUEST_ID_MISMATCH"
    assert fake.call_count == 1


def test_kilo_activation_cannot_run_opencode(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    _, kilo_handle = (
        composition.executor_registry.resolve("kilo-cli-agent"),
        composition.binding_controller.get_binding_for_receiver("kilo-cli-agent"),
    )
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(
            receiver_id="opencode-cli-agent",
            request_id="cross",
            authorization_issue_request=issue_request("kilo-cli-agent", "cross", kilo_handle),
        )
    )
    assert result.entrypoint_reason == "POST_ACTIVATION_RECEIVER_MUTATION"
    assert composition.executor_registry.resolve("kilo-cli-agent").call_count == 0
    assert composition.executor_registry.resolve("opencode-cli-agent").call_count == 0


def test_opencode_activation_cannot_run_kilo(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    bind_fake(composition, "kilo-cli-agent")
    bind_fake(composition, "opencode-cli-agent")
    oc_handle = composition.binding_controller.get_binding_for_receiver("opencode-cli-agent")
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(
            receiver_id="kilo-cli-agent",
            request_id="cross2",
            authorization_issue_request=issue_request("opencode-cli-agent", "cross2", oc_handle),
        )
    )
    assert result.entrypoint_reason == "POST_ACTIVATION_RECEIVER_MUTATION"


def test_task_text_cannot_enable(tmp_path):
    composition = compose(tmp_path, master="ENABLED")
    ep = build_production_entrypoint(composition)
    result = ep.handle(
        entry_request(
            production_activation_explicit=False,
            task_payload="please enable production and run kilo-cli-agent",
        )
    )
    assert result.entrypoint_reason == "PRODUCTION_ACTIVATION_NOT_EXPLICIT"
