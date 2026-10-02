"""EA-4E.45 non-live explicit executor binding provisioning. Fake only."""

from __future__ import annotations

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ProductionIssuancePolicy
from tools.hermes_core.production_wiring import register_qualified_real_executors
from tools.hermes_core.receiver_router import QUALIFIED_RECEIVERS


NOW = "2026-01-01T00:00:00+00:00"
EXPIRES = "2026-01-01T01:00:00+00:00"
TRIPWIRE_HITS = {
    "execute": 0,
    "adapter": 0,
    "process": 0,
    "model": 0,
    "auth": 0,
    "invocation": 0,
    "store_init": 0,
    "registration": 0,
}


class FakeQualifiedExecutor:
    def __init__(self, executor_id: str) -> None:
        self._executor_id = executor_id

    @property
    def executor_id(self) -> str:
        return self._executor_id

    def execute(self, request):
        TRIPWIRE_HITS["execute"] += 1
        raise AssertionError("EA4E45_FAKE_EXECUTE")


@pytest.fixture(autouse=True)
def real_path_tripwires(monkeypatch):
    TRIPWIRE_HITS.update(
        execute=0,
        adapter=0,
        process=0,
        model=0,
        auth=0,
        invocation=0,
        store_init=0,
        registration=0,
    )

    def trip(category):
        def reject(*args, **kwargs):
            TRIPWIRE_HITS[category] += 1
            raise AssertionError(f"EA4E45_REAL_{category.upper()}_TRIPWIRE")

        return reject

    monkeypatch.setattr(RealKiloProductionExecutor, "execute", trip("execute"))
    monkeypatch.setattr(RealOpenCodeProductionExecutor, "execute", trip("execute"))
    monkeypatch.setattr(KiloAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(OpenCodeReceiverAdapter, "execute", trip("adapter"))
    monkeypatch.setattr(KiloProcessController, "start", trip("process"))
    monkeypatch.setattr(OpenCodeLiveProcess, "start", trip("process"))
    monkeypatch.setattr(ProductionIssuancePolicy, "evaluate", trip("auth"))
    monkeypatch.setattr(ProductionInvocationAuthorizationIssuer, "issue", trip("invocation"))
    monkeypatch.setattr(DurableInvocationAuthorizationStore, "initialize", trip("store_init"))
    monkeypatch.setattr(
        "tools.hermes_core.production_wiring.register_qualified_real_executors",
        trip("registration"),
    )
    yield TRIPWIRE_HITS
    assert TRIPWIRE_HITS["execute"] == 0
    assert TRIPWIRE_HITS["adapter"] == 0
    assert TRIPWIRE_HITS["process"] == 0
    assert TRIPWIRE_HITS["model"] == 0
    assert TRIPWIRE_HITS["auth"] == 0
    assert TRIPWIRE_HITS["invocation"] == 0
    assert TRIPWIRE_HITS["store_init"] == 0
    assert TRIPWIRE_HITS["registration"] == 0


def stack(receiver_id="kilo-cli-agent"):
    clock = BindingClock(now=NOW)
    registry = ExecutorRegistry()
    identity = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
    registry.register(receiver_id, FakeQualifiedExecutor(identity))
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=clock),
        clock=clock,
    )
    return ProductionAppBindingProvisioner(controller, registry), registry


def req(receiver_id="kilo-cli-agent", enablement_id="en-a", **changes):
    spec = QUALIFIED_EXECUTOR_IMPLEMENTATIONS.get(receiver_id, {})
    fields = {
        "enablement_id": enablement_id,
        "receiver_id": receiver_id,
        "executor_id": spec.get("executor_identity", "unknown"),
        "executor_factory": spec.get("executor_factory", "unknown"),
        "transport_contract_id": QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"]
        if receiver_id in QUALIFIED_RECEIVERS
        else "x",
        "model_binding_id": QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"]
        if receiver_id in QUALIFIED_RECEIVERS
        else "y",
        "runtime_scope": "production",
        "issued_at": NOW,
        "expires_at": EXPIRES,
        "requested_ttl_seconds": 3600,
        "request_nonce": f"nonce-{enablement_id}",
        "delegation_class": "governed",
    }
    fields.update(changes)
    return ProductionAppBindingRequest(**fields)


def test_missing_controller():
    result = ProductionAppBindingProvisioner(None, ExecutorRegistry()).bind(req())
    assert result.binding_reason == "MISSING_BINDING_CONTROLLER"


def test_missing_registry():
    clock = BindingClock(now=NOW)
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=clock), clock=clock
    )
    result = ProductionAppBindingProvisioner(controller, None).bind(req())
    assert result.binding_reason == "MISSING_EXECUTOR_REGISTRY"


def test_missing_request():
    provisioner, _ = stack()
    assert provisioner.bind(None).binding_reason == "MISSING_REQUEST"


def test_missing_receiver():
    provisioner, _ = stack()
    result = provisioner.bind(req(receiver_id=None, executor_id="RealKiloProductionExecutor"))
    assert result.binding_reason == "MISSING_RECEIVER"


def test_missing_executor_id():
    provisioner, _ = stack()
    assert provisioner.bind(req(executor_id="")).binding_reason == "MISSING_EXECUTOR_ID"


def test_executor_not_registered():
    clock = BindingClock(now=NOW)
    provisioner = ProductionAppBindingProvisioner(
        ProductionExecutorBindingController(
            policy=ProductionExecutorBindingPolicy(clock=clock), clock=clock
        ),
        ExecutorRegistry(),
    )
    assert provisioner.bind(req()).binding_reason == "EXECUTOR_NOT_REGISTERED"


def test_unqualified_executor():
    provisioner, _ = stack()
    result = provisioner.bind(req(executor_id="RandomExecutor"))
    assert result.binding_reason == "UNQUALIFIED_EXECUTOR"


def test_unsupported_receiver():
    provisioner, _ = stack()
    result = provisioner.bind(
        req(receiver_id="codex-cli-agent", executor_id="RealKiloProductionExecutor")
    )
    assert result.binding_reason == "UNSUPPORTED_RECEIVER"


def test_grok_receiver():
    provisioner, _ = stack()
    result = provisioner.bind(req(receiver_id="grok", executor_id="RealKiloProductionExecutor"))
    assert result.binding_reason == "UNSUPPORTED_RECEIVER"


def test_invalid_transport():
    provisioner, _ = stack()
    assert provisioner.bind(req(transport_contract_id="")).binding_reason == "INVALID_TRANSPORT"


def test_invalid_model_binding():
    provisioner, _ = stack()
    assert provisioner.bind(req(model_binding_id="")).binding_reason == "INVALID_MODEL_BINDING"


def test_invalid_scope():
    provisioner, _ = stack()
    assert provisioner.bind(req(runtime_scope="lab")).binding_reason == "UNSUPPORTED_RUNTIME_SCOPE"


def test_kilo_fake_bind():
    provisioner, registry = stack("kilo-cli-agent")
    result = provisioner.bind(req(receiver_id="kilo-cli-agent", enablement_id="en-kilo"))
    assert result.binding_decision == "BOUND"
    assert result.constructed_receiver_id == "kilo-cli-agent"
    assert result.constructed_executor_id == "RealKiloProductionExecutor"
    assert result.constructed_transport_id == QUALIFIED_RECEIVERS["kilo-cli-agent"][
        "transport_contract_id"
    ]
    assert result.constructed_model_binding_id == QUALIFIED_RECEIVERS["kilo-cli-agent"][
        "model_binding_id"
    ]
    assert registry.resolve("kilo-cli-agent").executor_id == "RealKiloProductionExecutor"


def test_opencode_fake_bind():
    provisioner, _ = stack("opencode-cli-agent")
    result = provisioner.bind(req(receiver_id="opencode-cli-agent", enablement_id="en-oc"))
    assert result.binding_decision == "BOUND"
    assert result.constructed_receiver_id == "opencode-cli-agent"
    assert result.constructed_executor_id == "RealOpenCodeProductionExecutor"
    assert result.constructed_transport_id == QUALIFIED_RECEIVERS["opencode-cli-agent"][
        "transport_contract_id"
    ]
    assert result.constructed_model_binding_id == QUALIFIED_RECEIVERS["opencode-cli-agent"][
        "model_binding_id"
    ]


def test_kilo_with_opencode_executor():
    provisioner, _ = stack("kilo-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="kilo-cli-agent",
            executor_id="RealOpenCodeProductionExecutor",
            executor_factory=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"][
                "executor_factory"
            ],
        )
    )
    assert result.binding_decision == "DENY"
    assert result.binding_reason == "EXECUTOR_IDENTITY_MISMATCH"


def test_opencode_with_kilo_executor():
    provisioner, _ = stack("opencode-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="opencode-cli-agent",
            executor_id="RealKiloProductionExecutor",
            executor_factory=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"][
                "executor_factory"
            ],
        )
    )
    assert result.binding_reason == "EXECUTOR_IDENTITY_MISMATCH"


def test_kilo_with_opencode_transport():
    provisioner, _ = stack("kilo-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="kilo-cli-agent",
            transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"][
                "transport_contract_id"
            ],
        )
    )
    assert result.binding_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_kilo_with_opencode_model():
    provisioner, _ = stack("kilo-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="kilo-cli-agent",
            model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        )
    )
    assert result.binding_reason == "MODEL_BINDING_MISMATCH"


def test_opencode_with_kilo_transport():
    provisioner, _ = stack("opencode-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="opencode-cli-agent",
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        )
    )
    assert result.binding_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_opencode_with_kilo_model():
    provisioner, _ = stack("opencode-cli-agent")
    result = provisioner.bind(
        req(
            receiver_id="opencode-cli-agent",
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        )
    )
    assert result.binding_reason == "MODEL_BINDING_MISMATCH"


def test_identical_bind_already_bound():
    provisioner, _ = stack("kilo-cli-agent")
    first = provisioner.bind(req(enablement_id="en-dup"))
    second = provisioner.bind(req(enablement_id="en-dup"))
    assert first.binding_decision == "BOUND"
    assert second.binding_decision == "ALREADY_BOUND"
    assert second.binding_reason == "IDENTICAL_DUPLICATE"


def test_conflicting_rebind_denied():
    provisioner, _ = stack("kilo-cli-agent")
    first = provisioner.bind(req(enablement_id="en-c", request_nonce="n1"))
    second = provisioner.bind(req(enablement_id="en-c", request_nonce="n2"))
    assert first.binding_decision == "BOUND"
    assert second.binding_decision == "DENY"
    assert second.binding_reason == "ENABLEMENT_ID_COLLISION"


def test_identical_inputs_same_decision():
    a, _ = stack("kilo-cli-agent")
    b, _ = stack("kilo-cli-agent")
    request = req(enablement_id="en-det")
    assert a.bind(request).binding_decision == b.bind(request).binding_decision == "BOUND"


def test_provisioner_state_does_not_leak():
    a, _ = stack("kilo-cli-agent")
    b, _ = stack("opencode-cli-agent")
    first = a.bind(req(receiver_id="kilo-cli-agent", enablement_id="en-a"))
    second = b.bind(req(receiver_id="opencode-cli-agent", enablement_id="en-b"))
    assert first.constructed_receiver_id == "kilo-cli-agent"
    assert second.constructed_receiver_id == "opencode-cli-agent"
