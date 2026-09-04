"""EA-4E.17 production issuance policy tests."""

from __future__ import annotations

import pytest

from tools.hermes_core.production_issuance import (
    ClockCollaborator,
    ProductionIssuancePolicy,
    ProductionIssuanceRequest,
    compute_ea4e17_issuance_contract_id,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingResult,
    compute_ea4e6_router_contract_id,
)


def _make_request(
    receiver_id: str = "kilo-cli-agent",
    route_decision: str = "SELECTED",
    route_receiver: str | None = None,
    router_contract_id: str | None = None,
    transport_contract_id: str | None = None,
    model_binding_id: str | None = None,
    delegation_class: str = "governed",
    operation: str = "receiver-dispatch",
    execution_scope: str = "production",
    attempt_limit: int = 1,
    ttl: int = 3600,
    request_id: str = "req-001",
    nonce: str = "nonce-001",
) -> ProductionIssuanceRequest:
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return ProductionIssuanceRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        routing_result=RoutingResult(
            receiver_id=route_receiver or receiver_id,
            qualification_state="QUALIFIED",
            route_decision=route_decision,
            route_reason="test",
            execution_authority_present=True,
        ),
        router_contract_id=router_contract_id or compute_ea4e6_router_contract_id(),
        transport_contract_id=transport_contract_id or bindings.get("transport_contract_id", "unknown"),
        model_binding_id=model_binding_id or bindings.get("model_binding_id", "unknown"),
        delegation_class=delegation_class,
        requested_operation=operation,
        requested_execution_scope=execution_scope,
        requested_attempt_limit=attempt_limit,
        requested_authority_ttl_seconds=ttl,
        request_nonce=nonce,
    )


@pytest.fixture
def clock():
    return ClockCollaborator(now="2026-01-01T00:00:00Z")


@pytest.fixture
def policy(clock):
    return ProductionIssuancePolicy(clock=clock)


# --- Positive cases ---

def test_kilo_positive_issuance(policy):
    request = _make_request(receiver_id="kilo-cli-agent")
    result = policy.evaluate(request)
    assert result.policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True
    assert result.authority is not None
    assert result.activation is not None


def test_opencode_positive_issuance(policy):
    request = _make_request(receiver_id="opencode-cli-agent")
    result = policy.evaluate(request)
    assert result.policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True


# --- Fail-closed cases ---

def test_missing_receiver(policy):
    request = _make_request(receiver_id="")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MISSING_RECEIVER"


def test_unsupported_receiver(policy):
    request = _make_request(receiver_id="unknown-receiver")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "UNSUPPORTED_RECEIVER"


def test_route_not_selected(policy):
    request = _make_request(route_decision="REJECTED")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ROUTE_NOT_SELECTED"


def test_routing_receiver_mismatch(policy):
    request = _make_request(receiver_id="kilo-cli-agent", route_receiver="opencode-cli-agent")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ROUTING_RECEIVER_MISMATCH"


def test_router_contract_mismatch(policy):
    request = _make_request(router_contract_id="wrong")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ROUTER_CONTRACT_MISMATCH"


def test_transport_mismatch(policy):
    request = _make_request(transport_contract_id="wrong")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_model_binding_mismatch(policy):
    request = _make_request(model_binding_id="wrong")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MODEL_BINDING_MISMATCH"


def test_cross_receiver_binding_mismatch_kilo_with_opencode(policy):
    """Kilo receiver with OpenCode transport/model binding."""
    request = _make_request(
        receiver_id="kilo-cli-agent",
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
    )
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_cross_receiver_binding_mismatch_opencode_with_kilo(policy):
    """OpenCode receiver with Kilo transport/model binding."""
    request = _make_request(
        receiver_id="opencode-cli-agent",
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
    )
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_delegation_class_mismatch(policy):
    request = _make_request(delegation_class="unrestricted")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "DELEGATION_CLASS_MISMATCH"


def test_operation_mismatch(policy):
    request = _make_request(operation="admin")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "OPERATION_MISMATCH"


def test_execution_scope_mismatch(policy):
    request = _make_request(execution_scope="admin")
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EXECUTION_SCOPE_MISMATCH"


def test_attempt_limit_zero(policy):
    request = _make_request(attempt_limit=0)
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ATTEMPT_LIMIT_ZERO"


def test_attempt_limit_above_max(policy):
    request = _make_request(attempt_limit=2)
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ATTEMPT_LIMIT_ABOVE_MAX"


def test_invalid_ttl_zero(policy):
    request = _make_request(ttl=0)
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "INVALID_TTL"


def test_invalid_ttl_negative(policy):
    request = _make_request(ttl=-1)
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "INVALID_TTL"


def test_ttl_above_max(policy):
    request = _make_request(ttl=7200)
    result = policy.evaluate(request)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TTL_ABOVE_MAX"


# --- Determinism ---

def test_deterministic_repeated_decision(policy):
    request = _make_request()
    result1 = policy.evaluate(request)
    result2 = policy.evaluate(request)
    assert result1.policy_decision == result2.policy_decision
    assert result1.policy_reason == result2.policy_reason


def test_deterministic_cross_instance(clock):
    request = _make_request()
    policy1 = ProductionIssuancePolicy(clock=clock)
    policy2 = ProductionIssuancePolicy(clock=clock)
    result1 = policy1.evaluate(request)
    result2 = policy2.evaluate(request)
    assert result1.policy_decision == result2.policy_decision


# --- No execution ---

def test_no_execution_on_positive(policy):
    request = _make_request()
    result = policy.evaluate(request)
    # Policy does not execute anything
    assert result.authority is not None
    assert result.activation is not None
    # No process started, no model invoked (implicit by design)


def test_no_execution_on_rejection(policy):
    request = _make_request(receiver_id="unknown")
    result = policy.evaluate(request)
    assert result.authority_issued is False
    assert result.activation_issued is False


# --- Issuance contract ---

def test_issuance_contract_deterministic():
    id1 = compute_ea4e17_issuance_contract_id()
    id2 = compute_ea4e17_issuance_contract_id()
    assert id1 == id2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
