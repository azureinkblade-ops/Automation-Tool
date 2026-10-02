"""EA-4E.48 retry fake E2E through the real app layers. Fake executors only."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_authority import ProductionAppAuthorityCollaborator
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_app_config import (
    ProductionAppRuntimeConfig,
    build_factory_config,
)
from tools.hermes_core.production_app_factory import ProductionAppFactory
from tools.hermes_core.production_app_invocation_authorization import (
    ProductionAppInvocationAuthorizationProvisioner,
    ProductionAppInvocationAuthorizationRequest,
)
from tools.hermes_core.production_app_user_action import ProductionAppUserActionRequest
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_auth_store_bootstrap import (
    ProductionInvocationAuthStoreBootstrapRequest,
    ProductionInvocationAuthStoreBootstrapper,
)
from tools.hermes_core.production_issuance import ClockCollaborator, QUALIFIED_RECEIVERS
from tools.hermes_core.production_wiring import ProductionWiringConfig
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


NOW = "2026-01-01T00:00:00+00:00"
ISSUED = "2025-12-31T23:30:00+00:00"
EXPIRES = "2026-01-01T00:30:00+00:00"
TRIPWIRE_HITS = {
    "real_execute": 0,
    "adapter": 0,
    "process": 0,
    "registration": 0,
}


class FakeQualifiedExecutor:
    def __init__(self, executor_id: str) -> None:
        self._executor_id = executor_id
        self.calls = 0

    @property
    def executor_id(self) -> str:
        return self._executor_id

    def execute(self, request):
        self.calls += 1
        from tools.hermes_core.production_executor_binding import ProductionExecutorResult

        return ProductionExecutorResult(
            executor_id=self._executor_id,
            execution_status="SUCCESS",
            output="EA4E48_FAKE_E2E_OK",
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(real_execute=0, adapter=0, process=0, registration=0)

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E48_REAL_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "execute", trip("real_execute"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", trip("real_execute"))
    monkeypatch.setattr(KiloAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", trip("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", trip("process"))
    monkeypatch.setattr(
        "tools.hermes_core.production_wiring.register_qualified_real_executors",
        trip("registration"),
    )
    yield TRIPWIRE_HITS
    assert TRIPWIRE_HITS["real_execute"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["registration"] == 0


def bootstrap_store(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store_path = tmp_path / "ea4e48.auth.sqlite"
    anchor_path = tmp_path / "ea4e48.auth.anchor"
    result = ProductionInvocationAuthStoreBootstrapper().bootstrap(
        ProductionInvocationAuthStoreBootstrapRequest(
            store_path=store_path,
            anchor_path=anchor_path,
            bootstrap_explicit=True,
        )
    )
    assert result.bootstrap_decision == "INITIALIZED"
    return store_path, anchor_path


def assemble(tmp_path: Path, receiver_id: str, *, feature_gate="ENABLED", master="ENABLED"):
    store_path, anchor_path = bootstrap_store(tmp_path)
    registry = ExecutorRegistry()
    fake = FakeQualifiedExecutor(
        QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
    )
    registry.register(receiver_id, fake)
    clock = ClockCollaborator(now=NOW)
    components = ProductionAppFactory.build(
        build_factory_config(
            ProductionAppRuntimeConfig(
                wiring=ProductionWiringConfig(
                    master_enable=master,
                    auth_store_path=store_path,
                    auth_anchor_path=anchor_path,
                ),
                clock=clock,
                callsite_feature_gate=feature_gate,
                executor_registry=registry,
                register_real_executors=False,
            )
        )
    )
    bind_result = ProductionAppBindingProvisioner(
        components.composition.binding_controller,
        components.composition.executor_registry,
    ).bind(
        ProductionAppBindingRequest(
            enablement_id=f"en-{receiver_id}",
            receiver_id=receiver_id,
            executor_id=QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"],
            executor_factory=QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id][
                "executor_factory"
            ],
            transport_contract_id=QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"],
            runtime_scope="production",
            issued_at=ISSUED,
            expires_at=EXPIRES,
            requested_ttl_seconds=3600,
            request_nonce=f"bind-{receiver_id}",
            delegation_class="governed",
        )
    )
    return components, fake, bind_result, clock


def provision_issue(receiver_id, request_id, authority, handle):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    result = ProductionAppInvocationAuthorizationProvisioner(BindingClock(now=NOW)).provision(
        ProductionAppInvocationAuthorizationRequest(
            issue_request_id=f"issue-{request_id}",
            execution_request_id=request_id,
            receiver_id=receiver_id,
            execution_authority=authority,
            binding_handle=handle,
            transport_contract_id=spec["transport_contract_id"],
            model_binding_id=spec["model_binding_id"],
            runtime_scope="production",
            requested_operation="receiver-dispatch",
            requested_ttl_seconds=60,
            attempt_number=1,
            nonce=f"inv-{request_id}",
            delegation_class="governed",
        )
    )
    return result


def submit_e2e(tmp_path, receiver_id, request_id, **request_changes):
    components, fake, bind_result, clock = assemble(tmp_path, receiver_id)
    assert bind_result.binding_decision == "BOUND"
    authority, activation = external_authority_and_activation(
        receiver_id, request_id, clock=clock
    )
    provisioned = provision_issue(receiver_id, request_id, authority, bind_result.handle)
    assert provisioned.provisioning_decision == "PROVISIONED"
    fields = {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "task_payload": "EA4E48_FAKE_E2E",
        "production_activation_explicit": True,
        "runtime_scope": "production",
        "authorization_issue_request": provisioned.issue_request,
        "transport_contract_id": QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"],
        "model_binding_id": QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"],
        "execution_authority": authority,
        "activation": activation,
    }
    fields.update(request_changes)
    result = components.user_action.submit(ProductionAppUserActionRequest(**fields))
    return result, fake, components


def test_import_has_no_receiver_or_model_side_effects():
    import tools.hermes_core.governed_production_runtime as runtime
    import tools.hermes_core.production_app_factory as factory
    import tools.hermes_core.production_app_user_action as user_action

    assert runtime is not None
    assert factory is not None
    assert user_action is not None
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["real_execute"] == 0
    assert TRIPWIRE_HITS["registration"] == 0


def test_kilo_fake_e2e_reaches_execution_boundary(tmp_path):
    result, fake, _ = submit_e2e(tmp_path, "kilo-cli-agent", "ea4e48-kilo")
    assert result.user_action_decision == "ALLOW"
    assert fake.calls == 1
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["real_execute"] == 0


def test_opencode_fake_e2e_reaches_execution_boundary(tmp_path):
    result, fake, _ = submit_e2e(tmp_path, "opencode-cli-agent", "ea4e48-oc")
    assert result.user_action_decision == "ALLOW"
    assert fake.calls == 1
    assert TRIPWIRE_HITS["process"] == 0


def test_valid_authority_activation_disabled_denies(tmp_path):
    components, _, bind_result, clock = assemble(tmp_path, "kilo-cli-agent")
    authority, activation = external_authority_and_activation(
        "kilo-cli-agent", "ea4e48-act-off", clock=clock
    )
    from dataclasses import replace

    disabled = replace(activation, activation_mode="DISABLED")
    provisioned = provision_issue(
        "kilo-cli-agent", "ea4e48-act-off", authority, bind_result.handle
    )
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e48-act-off",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
            authorization_issue_request=provisioned.issue_request,
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"][
                "transport_contract_id"
            ],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            execution_authority=authority,
            activation=disabled,
        )
    )
    assert result.user_action_decision == "DENY"


def test_missing_authority_denies(tmp_path):
    result, fake, _ = submit_e2e(
        tmp_path, "kilo-cli-agent", "ea4e48-no-auth", execution_authority=None
    )
    assert result.user_action_decision == "DENY"
    assert fake.calls == 0


def test_missing_activation_denies(tmp_path):
    result, fake, _ = submit_e2e(
        tmp_path, "kilo-cli-agent", "ea4e48-no-act", activation=None
    )
    assert result.user_action_decision == "DENY"
    assert fake.calls == 0


def test_feature_gate_disabled_denies(tmp_path):
    components, fake, bind_result, clock = assemble(
        tmp_path, "kilo-cli-agent", feature_gate="DISABLED"
    )
    authority, activation = external_authority_and_activation(
        "kilo-cli-agent", "ea4e48-gate", clock=clock
    )
    provisioned = provision_issue(
        "kilo-cli-agent", "ea4e48-gate", authority, bind_result.handle
    )
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e48-gate",
            receiver_id="kilo-cli-agent",
            production_activation_explicit=True,
            authorization_issue_request=provisioned.issue_request,
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"][
                "transport_contract_id"
            ],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            execution_authority=authority,
            activation=activation,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "OUTER_FEATURE_GATE_DISABLED"
    assert fake.calls == 0


def test_grok_user_action_denies(tmp_path):
    components, fake, _, _ = assemble(tmp_path, "kilo-cli-agent")
    result = components.user_action.submit(
        ProductionAppUserActionRequest(
            request_id="ea4e48-grok",
            receiver_id="grok",
            production_activation_explicit=True,
        )
    )
    assert result.user_action_decision == "DENY"
    assert result.user_action_reason == "UNSUPPORTED_RECEIVER"
    assert fake.calls == 0


def test_missing_store_fails_closed(tmp_path):
    registry = ExecutorRegistry()
    with pytest.raises(Exception):
        ProductionAppFactory.build(
            build_factory_config(
                ProductionAppRuntimeConfig(
                    wiring=ProductionWiringConfig(
                        master_enable="ENABLED",
                        auth_store_path=tmp_path / "missing.sqlite",
                        auth_anchor_path=tmp_path / "missing.anchor",
                    ),
                    clock=ClockCollaborator(now=NOW),
                    callsite_feature_gate="ENABLED",
                    executor_registry=registry,
                    register_real_executors=False,
                )
            )
        )


def test_identical_inputs_same_decision(tmp_path):
    first, _, _ = submit_e2e(tmp_path / "graph-a", "kilo-cli-agent", "ea4e48-det-a")
    second, _, _ = submit_e2e(tmp_path / "graph-b", "kilo-cli-agent", "ea4e48-det-a")
    assert first.user_action_decision == second.user_action_decision == "ALLOW"
