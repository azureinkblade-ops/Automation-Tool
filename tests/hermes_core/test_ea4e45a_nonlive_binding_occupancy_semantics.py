"""EA-4E.45A registry occupancy vs active binding occupancy. Fake only."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tools.hermes_core.durable_invocation_authorization_store import (
    DurableInvocationAuthorizationStore,
)
from tools.hermes_core.kilo_adapter import KiloAdapter, KiloProcessController
from tools.hermes_core.kilo_live_binding import RealKiloProductionExecutor
from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess, OpenCodeReceiverAdapter
from tools.hermes_core.opencode_live_binding import RealOpenCodeProductionExecutor
from tools.hermes_core.production_executor_binding import (
    ALLOWED_DELEGATION_CLASS,
    ALLOWED_RUNTIME_SCOPE,
    MAX_SIMULTANEOUS_REAL_BINDINGS,
    BindingClock,
    BindingPolicyError,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssuer,
)
from tools.hermes_core.production_issuance import ProductionIssuancePolicy, QUALIFIED_RECEIVERS


NOW = "2026-01-01T00:00:00+00:00"
ISSUED = "2025-12-31T23:30:00+00:00"
EXPIRES = "2026-01-01T00:30:00+00:00"
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
        raise AssertionError("EA4E45A_FAKE_EXECUTE")


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
            raise AssertionError(f"EA4E45A_REAL_{category.upper()}_TRIPWIRE")

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
    assert MAX_SIMULTANEOUS_REAL_BINDINGS == 1


def controller_stack():
    clock = BindingClock(now=NOW)
    registry = ExecutorRegistry()
    controller = ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=clock),
        clock=clock,
    )
    return controller, registry


def enablement(receiver_id="kilo-cli-agent", enablement_id="en-a", **changes):
    spec = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    kwargs = {
        "enablement_id": enablement_id,
        "receiver_id": receiver_id,
        "transport_contract_id": QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"],
        "model_binding_id": QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"],
        "executor_identity": spec["executor_identity"],
        "executor_factory": spec["executor_factory"],
        "runtime_scope": ALLOWED_RUNTIME_SCOPE,
        "delegation_class": ALLOWED_DELEGATION_CLASS,
        "requested_ttl_seconds": Decimal("3600"),
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "request_nonce": f"nonce-{enablement_id}",
    }
    kwargs.update(changes)
    return ProductionExecutorBindingEnablement(**kwargs)


def pre_register(registry, receiver_id):
    identity = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
    fake = FakeQualifiedExecutor(identity)
    registry.register(receiver_id, fake)
    return fake


def test_empty_registry_zero_active_bindings():
    controller, registry = controller_stack()
    assert registry.bound_count == 0
    assert controller.active_binding_count == 0


def test_one_registration_zero_active_bindings():
    controller, registry = controller_stack()
    pre_register(registry, "kilo-cli-agent")
    assert registry.bound_count == 1
    assert controller.active_binding_count == 0


def test_two_registrations_zero_active_bindings():
    controller, registry = controller_stack()
    pre_register(registry, "kilo-cli-agent")
    pre_register(registry, "opencode-cli-agent")
    assert registry.bound_count == 2
    assert controller.active_binding_count == 0


def test_first_kilo_bind_after_pre_registration():
    controller, registry = controller_stack()
    fake = pre_register(registry, "kilo-cli-agent")
    handle = controller.bind(
        enablement("kilo-cli-agent", "en-kilo"),
        registry,
        executor_factory=lambda: fake,
    )
    assert handle.receiver_id == "kilo-cli-agent"
    assert controller.active_binding_count == 1
    assert registry.bound_count == 1


def test_first_opencode_bind_isolated_state():
    controller, registry = controller_stack()
    fake = pre_register(registry, "opencode-cli-agent")
    handle = controller.bind(
        enablement("opencode-cli-agent", "en-oc"),
        registry,
        executor_factory=lambda: fake,
    )
    assert handle.receiver_id == "opencode-cli-agent"
    assert controller.active_binding_count == 1


def test_second_distinct_bind_hits_limit():
    controller, registry = controller_stack()
    kilo = pre_register(registry, "kilo-cli-agent")
    opencode = pre_register(registry, "opencode-cli-agent")
    controller.bind(
        enablement("kilo-cli-agent", "en-kilo"),
        registry,
        executor_factory=lambda: kilo,
    )
    assert controller.active_binding_count == 1
    with pytest.raises(BindingPolicyError) as exc:
        controller.bind(
            enablement("opencode-cli-agent", "en-oc"),
            registry,
            executor_factory=lambda: opencode,
        )
    assert exc.value.reason == "BINDING_LIMIT_EXCEEDED"
    assert controller.active_binding_count == 1


def test_opencode_first_then_kilo_hits_limit():
    controller, registry = controller_stack()
    kilo = pre_register(registry, "kilo-cli-agent")
    opencode = pre_register(registry, "opencode-cli-agent")
    controller.bind(
        enablement("opencode-cli-agent", "en-oc"),
        registry,
        executor_factory=lambda: opencode,
    )
    with pytest.raises(BindingPolicyError) as exc:
        controller.bind(
            enablement("kilo-cli-agent", "en-kilo"),
            registry,
            executor_factory=lambda: kilo,
        )
    assert exc.value.reason == "BINDING_LIMIT_EXCEEDED"
    assert controller.active_binding_count == 1


def test_identical_duplicate_does_not_increment_active_count():
    controller, registry = controller_stack()
    fake = pre_register(registry, "kilo-cli-agent")
    first = controller.bind(
        enablement("kilo-cli-agent", "en-dup"),
        registry,
        executor_factory=lambda: fake,
    )
    second = controller.bind(
        enablement("kilo-cli-agent", "en-dup"),
        registry,
        executor_factory=lambda: fake,
    )
    assert first.binding_id == second.binding_id
    assert controller.active_binding_count == 1


def test_conflicting_rebind_denied_original_preserved():
    controller, registry = controller_stack()
    fake = pre_register(registry, "kilo-cli-agent")
    first = controller.bind(
        enablement("kilo-cli-agent", "en-c", request_nonce="n1"),
        registry,
        executor_factory=lambda: fake,
    )
    with pytest.raises(BindingPolicyError) as exc:
        controller.bind(
            enablement("kilo-cli-agent", "en-c", request_nonce="n2"),
            registry,
            executor_factory=lambda: fake,
        )
    assert exc.value.reason == "ENABLEMENT_ID_COLLISION"
    assert controller.active_binding_count == 1
    assert controller.get_bound_handle("en-c").binding_id == first.binding_id


def test_limit_constant_unchanged():
    assert MAX_SIMULTANEOUS_REAL_BINDINGS == 1
