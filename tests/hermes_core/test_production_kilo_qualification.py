"""EA-4E.12 pre-live negative gate tests."""

from __future__ import annotations

from tools.hermes_core.production_kilo_qualification import ProductionKiloQualificationHarness
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    build_dispatch_authority,
)
from tools.hermes_core.production_activation import build_production_activation
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id


def _build_auth(receiver_id: str, nonce: str = "test"):
    return build_dispatch_authority(
        receiver_id=receiver_id,
        transport_contract_id=QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"],
        router_contract_id=compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(operation="receiver-dispatch", receiver_id=receiver_id),
        delegation_class="governed",
        decision="GRANTED",
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        nonce=nonce,
    )


def _build_activation(receiver_id: str, mode: str = "ENABLED", **overrides):
    kwargs = dict(
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS[receiver_id]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS[receiver_id]["model_binding_id"],
        activation_mode=mode,
        execution_scope="production",
        delegation_class="governed",
    )
    kwargs.update(overrides)
    return build_production_activation(**kwargs)


def test_missing_activation():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate1")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=None)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "PRODUCTION_ACTIVATION_MISSING"
    assert harness.invocation_count == 0


def test_disabled_activation():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate2")
    act = _build_activation("kilo-cli-agent", "DISABLED")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "PRODUCTION_ACTIVATION_DISABLED"
    assert harness.invocation_count == 0


def test_missing_authority():
    harness = ProductionKiloQualificationHarness()
    act = _build_activation("kilo-cli-agent", "ENABLED")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=None, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "EXECUTION_AUTHORITY_MISSING"
    assert harness.invocation_count == 0


def test_authority_receiver_mismatch():
    harness = ProductionKiloQualificationHarness()
    wrong_auth = _build_auth("opencode-cli-agent", "gate4")
    act = _build_activation("kilo-cli-agent", "ENABLED")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=wrong_auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "AUTHORITY_RECEIVER_MISMATCH"
    assert harness.invocation_count == 0


def test_activation_receiver_mismatch():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate5")
    wrong_act = _build_activation("opencode-cli-agent", "ENABLED")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=wrong_act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "ACTIVATION_RECEIVER_MISMATCH"
    assert harness.invocation_count == 0


def test_router_contract_mismatch():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate6")
    act = _build_activation("kilo-cli-agent", "ENABLED", router_contract_id="wrong")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "ROUTER_CONTRACT_MISMATCH"
    assert harness.invocation_count == 0


def test_authority_contract_mismatch():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate7")
    act = _build_activation("kilo-cli-agent", "ENABLED", authority_contract_id="wrong")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "AUTHORITY_CONTRACT_MISMATCH"
    assert harness.invocation_count == 0


def test_transport_mismatch():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate8")
    act = _build_activation("kilo-cli-agent", "ENABLED", transport_contract_id="wrong")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "TRANSPORT_CONTRACT_MISMATCH"
    assert harness.invocation_count == 0


def test_model_binding_mismatch():
    harness = ProductionKiloQualificationHarness()
    auth = _build_auth("kilo-cli-agent", "gate9")
    act = _build_activation("kilo-cli-agent", "ENABLED", model_binding_id="wrong")
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=auth, activation=act)
    assert r.dispatch_decision == "REJECT"
    assert r.reason == "MODEL_BINDING_MISMATCH"
    assert harness.invocation_count == 0


def test_unsupported_receiver():
    harness = ProductionKiloQualificationHarness()
    r = harness.dispatch(receiver_id="unknown", authority=None, activation=None)
    assert r.dispatch_decision == "REJECT"
    assert harness.invocation_count == 0


def test_no_fallback():
    harness = ProductionKiloQualificationHarness()
    r = harness.dispatch(receiver_id="kilo-cli-agent", authority=None, activation=None)
    assert r.dispatch_decision == "REJECT"
    assert harness.invocation_count == 0


if __name__ == "__main__":
    test_missing_activation()
    test_disabled_activation()
    test_missing_authority()
    test_authority_receiver_mismatch()
    test_activation_receiver_mismatch()
    test_router_contract_mismatch()
    test_authority_contract_mismatch()
    test_transport_mismatch()
    test_model_binding_mismatch()
    test_unsupported_receiver()
    test_no_fallback()
    print("ALL PRE-LIVE NEGATIVE GATES PASSED")
