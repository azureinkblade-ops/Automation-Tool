"""EA-4E.15 pre-live negative gate tests."""

from __future__ import annotations

from tools.hermes_core.kilo_live_binding import KiloLiveBindingHarness
from tools.hermes_core.production_execution import ProductionExecutionRequest
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


def _build_request(receiver_id: str, attempt_limit: int = 1):
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return ProductionExecutionRequest(
        receiver_id=receiver_id,
        delegation_id="delegation-ea4e15",
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=bindings.get("transport_contract_id", "unknown"),
        model_binding_id=bindings.get("model_binding_id", "unknown"),
        execution_scope="production",
        task_payload="Return exactly: EA4E15_KILO_EXECUTION_BOUNDARY_OK",
        attempt_limit=attempt_limit,
    )


def test_missing_receiver():
    harness = KiloLiveBindingHarness()
    result = harness.execute(
        receiver_id="",
        authority=None,
        activation=None,
        execution_request=_build_request(""),
    )
    assert result.execution_decision == "REJECT"
    assert result.real_adapter_called is False


def test_unsupported_receiver():
    harness = KiloLiveBindingHarness()
    result = harness.execute(
        receiver_id="unknown",
        authority=None,
        activation=None,
        execution_request=_build_request("unknown"),
    )
    assert result.execution_decision == "REJECT"
    assert result.real_adapter_called is False


def test_missing_authority():
    harness = KiloLiveBindingHarness()
    activation = _build_activation("kilo-cli-agent", "ENABLED")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=None,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "EXECUTION_AUTHORITY_MISSING"
    assert result.real_adapter_called is False


def test_denied_authority():
    harness = KiloLiveBindingHarness()
    denied_auth = build_dispatch_authority(
        receiver_id="kilo-cli-agent",
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        router_contract_id=compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(operation="receiver-dispatch", receiver_id="kilo-cli-agent"),
        delegation_class="governed",
        decision="DENIED",
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        nonce="denied",
    )
    activation = _build_activation("kilo-cli-agent", "ENABLED")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=denied_auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "EXECUTION_AUTHORITY_DENIED"
    assert result.real_adapter_called is False


def test_authority_receiver_mismatch():
    harness = KiloLiveBindingHarness()
    wrong_auth = _build_auth("opencode-cli-agent", "mismatch")
    activation = _build_activation("kilo-cli-agent", "ENABLED")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=wrong_auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "AUTHORITY_RECEIVER_MISMATCH"
    assert result.real_adapter_called is False


def test_missing_activation():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "missing-act")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=None,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "PRODUCTION_ACTIVATION_MISSING"
    assert result.real_adapter_called is False


def test_disabled_activation():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "disabled-act")
    activation = _build_activation("kilo-cli-agent", "DISABLED")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "PRODUCTION_ACTIVATION_DISABLED"
    assert result.real_adapter_called is False


def test_activation_receiver_mismatch():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "act-mismatch")
    wrong_activation = _build_activation("opencode-cli-agent", "ENABLED")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=wrong_activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "ACTIVATION_RECEIVER_MISMATCH"
    assert result.real_adapter_called is False


def test_router_contract_mismatch():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "router-mm")
    activation = _build_activation("kilo-cli-agent", "ENABLED", router_contract_id="wrong")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "ROUTER_CONTRACT_MISMATCH"
    assert result.real_adapter_called is False


def test_authority_contract_mismatch():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "auth-mm")
    activation = _build_activation("kilo-cli-agent", "ENABLED", authority_contract_id="wrong")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "AUTHORITY_CONTRACT_MISMATCH"
    assert result.real_adapter_called is False


def test_transport_mismatch():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "transport-mm")
    activation = _build_activation("kilo-cli-agent", "ENABLED", transport_contract_id="wrong")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "TRANSPORT_CONTRACT_MISMATCH"
    assert result.real_adapter_called is False


def test_model_binding_mismatch():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "model-mm")
    activation = _build_activation("kilo-cli-agent", "ENABLED", model_binding_id="wrong")
    request = _build_request("kilo-cli-agent")
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason == "MODEL_BINDING_MISMATCH"
    assert result.real_adapter_called is False


def test_execution_budget_exhausted():
    harness = KiloLiveBindingHarness()
    auth = _build_auth("kilo-cli-agent", "budget")
    activation = _build_activation("kilo-cli-agent", "ENABLED")
    request = _build_request("kilo-cli-agent", attempt_limit=0)
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=auth,
        activation=activation,
        execution_request=request,
    )
    assert result.execution_decision == "REJECT"
    assert result.reason in ("LIVE_INVOCATION_BUDGET_EXHAUSTED", "EXECUTION_BUDGET_EXHAUSTED")
    assert result.real_adapter_called is False


def test_no_opencode_fallback():
    """Kilo rejection does not fall back to OpenCode."""
    harness = KiloLiveBindingHarness()
    result = harness.execute(
        receiver_id="kilo-cli-agent",
        authority=None,
        activation=None,
        execution_request=_build_request("kilo-cli-agent"),
    )
    assert result.execution_decision == "REJECT"
    assert harness.invocation_count == 0


if __name__ == "__main__":
    test_missing_receiver()
    test_unsupported_receiver()
    test_missing_authority()
    test_denied_authority()
    test_authority_receiver_mismatch()
    test_missing_activation()
    test_disabled_activation()
    test_activation_receiver_mismatch()
    test_router_contract_mismatch()
    test_authority_contract_mismatch()
    test_transport_mismatch()
    test_model_binding_mismatch()
    test_execution_budget_exhausted()
    test_no_opencode_fallback()
    print("ALL PRE-LIVE NEGATIVE GATES PASSED")
