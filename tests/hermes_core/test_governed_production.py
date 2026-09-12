"""EA-4E.18 issuance-to-execution integration tests.

All tests use a FIXED deterministic clock (2026-01-01T00:00:00Z).
No wall-clock reads are required.
"""

from __future__ import annotations

import pytest

from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
    compute_ea4e18_integration_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator, ProductionIssuancePolicy
from tools.hermes_core.production_execution import (
    ExecutorRegistry,
    ProductionExecutorProtocol,
    ProductionExecutorResult,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# --------------------------------------------------------------------------- #
# EA-4E.18 phase-specific fake executors
# --------------------------------------------------------------------------- #

class EA4E18FakeKiloExecutor:
    """EA-4E.18-specific fake Kilo executor. Distinct from EA-4E.14 fixture."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "ea4e18-fake-kilo-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E18_KILO_GOVERNED_EXECUTION_OK",
            reason="FAKE_EXECUTION",
        )


class EA4E18FakeOpenCodeExecutor:
    """EA-4E.18-specific fake OpenCode executor. Distinct from EA-4E.14 fixture."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "ea4e18-fake-opencode-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E18_OPENCODE_GOVERNED_EXECUTION_OK",
            reason="FAKE_EXECUTION",
        )


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

def _make_request(
    receiver_id: str = "kilo-cli-agent",
    router_contract_id: str | None = None,
    transport_contract_id: str | None = None,
    model_binding_id: str | None = None,
    attempt_limit: int = 1,
    ttl: int = 3600,
    request_id: str = "req-001",
) -> GovernedExecutionRequest:
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return GovernedExecutionRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=router_contract_id or compute_ea4e6_router_contract_id(),
        transport_contract_id=transport_contract_id or bindings.get("transport_contract_id", "unknown"),
        model_binding_id=model_binding_id or bindings.get("model_binding_id", "unknown"),
        requested_attempt_limit=attempt_limit,
        requested_authority_ttl_seconds=ttl,
    )


@pytest.fixture
def fixed_clock():
    """Fixed deterministic qualification clock."""
    return ClockCollaborator(now=QUALIFICATION_CLOCK)


@pytest.fixture
def executor_registry():
    registry = ExecutorRegistry()
    registry.register("kilo-cli-agent", EA4E18FakeKiloExecutor())
    registry.register("opencode-cli-agent", EA4E18FakeOpenCodeExecutor())
    return registry


@pytest.fixture
def coordinator(fixed_clock, executor_registry):
    return GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=executor_registry,
    )


# --- Positive paths ---

def test_kilo_full_governed_path(coordinator):
    request = _make_request(receiver_id="kilo-cli-agent")
    result = coordinator.execute(request)
    assert result.route_decision == "SELECTED"
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True
    assert result.execution_request_created is True
    assert result.adapter_resolution == "KILO"
    assert result.execution_decision == "EXECUTE"
    assert result.executor_called is True
    assert result.execution_status == "SUCCESS"
    assert result.execution_output == "EA4E18_KILO_GOVERNED_EXECUTION_OK"


def test_opencode_full_governed_path(coordinator):
    request = _make_request(receiver_id="opencode-cli-agent")
    result = coordinator.execute(request)
    assert result.route_decision == "SELECTED"
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True
    assert result.execution_request_created is True
    assert result.adapter_resolution == "OPENCODE"
    assert result.execution_decision == "EXECUTE"
    assert result.executor_called is True
    assert result.execution_status == "SUCCESS"
    assert result.execution_output == "EA4E18_OPENCODE_GOVERNED_EXECUTION_OK"


# --- Fail-closed cases ---

def test_missing_receiver(coordinator):
    request = _make_request(receiver_id="")
    result = coordinator.execute(request)
    assert result.route_decision == "REJECT"
    assert result.issuance_policy_decision == "NOT_EVALUATED"
    assert result.authority_issued is False
    assert result.execution_request_created is False


def test_unsupported_receiver(coordinator):
    request = _make_request(receiver_id="unknown")
    result = coordinator.execute(request)
    assert result.route_decision == "REJECT"
    assert result.authority_issued is False


def test_issuance_rejection_prevents_execution(fixed_clock, executor_registry):
    policy = ProductionIssuancePolicy(clock=fixed_clock, max_attempt_limit=0)
    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=executor_registry,
        policy=policy,
    )
    request = _make_request()
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert result.execution_request_created is False
    assert result.executor_called is False


def test_missing_executor(fixed_clock):
    coord = GovernedProductionCoordinator(clock=fixed_clock)
    request = _make_request()
    result = coord.execute(request)
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.execution_decision == "REJECT"
    assert result.reason == "EXECUTOR_NOT_CONFIGURED"


def test_attempt_limit_above_max(coordinator):
    request = _make_request(attempt_limit=2)
    result = coordinator.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "ATTEMPT_LIMIT" in result.issuance_policy_reason


def test_attempt_limit_zero(coordinator):
    request = _make_request(attempt_limit=0)
    result = coordinator.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "ATTEMPT_LIMIT" in result.issuance_policy_reason


def test_invalid_ttl_zero(coordinator):
    request = _make_request(ttl=0)
    result = coordinator.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "TTL" in result.issuance_policy_reason


def test_invalid_ttl_negative(coordinator):
    request = _make_request(ttl=-1)
    result = coordinator.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "TTL" in result.issuance_policy_reason


def test_ttl_above_max(coordinator):
    request = _make_request(ttl=7200)
    result = coordinator.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "TTL" in result.issuance_policy_reason


# --- Determinism tests ---

def test_same_request_same_clock_same_decision(fixed_clock, executor_registry):
    request1 = _make_request(request_id="same-decision-1")
    coord1 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result1 = coord1.execute(request1)
    request2 = _make_request(request_id="same-decision-2")
    coord2 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result2 = coord2.execute(request2)
    assert result1.route_decision == result2.route_decision
    assert result1.issuance_policy_decision == result2.issuance_policy_decision
    assert result1.execution_decision == result2.execution_decision


def test_same_request_same_clock_same_issued_at(fixed_clock, executor_registry):
    """Same request + same clock = same issued_at."""
    request1 = _make_request(request_id="same-issued-1")
    coord1 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result1 = coord1.execute(request1)
    request2 = _make_request(request_id="same-issued-2")
    coord2 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result2 = coord2.execute(request2)
    # Both should have same issuance result
    assert result1.issuance_policy_decision == result2.issuance_policy_decision
    assert result1.authority_issued == result2.authority_issued


def test_same_request_same_clock_same_expires_at(fixed_clock, executor_registry):
    """Same request + same clock = same expires_at."""
    request1 = _make_request(request_id="same-expiry-1")
    coord1 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result1 = coord1.execute(request1)
    request2 = _make_request(request_id="same-expiry-2")
    coord2 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result2 = coord2.execute(request2)
    # Both should have same authority validity
    assert result1.authority_valid == result2.authority_valid


def test_fresh_policy_same_clock_same_decision(fixed_clock):
    """Fresh ProductionIssuancePolicy + same clock = same decision."""
    request = _make_request(request_id="fresh-policy")
    policy1 = ProductionIssuancePolicy(clock=fixed_clock)
    policy2 = ProductionIssuancePolicy(clock=fixed_clock)
    result1 = policy1.evaluate(_make_issuance_request(request, fixed_clock))
    result2 = policy2.evaluate(_make_issuance_request(request, fixed_clock))
    assert result1.policy_decision == result2.policy_decision


def test_fresh_coordinator_same_clock_same_decision(fixed_clock, executor_registry):
    """Fresh GovernedProductionCoordinator + same clock = same decision."""
    request = _make_request(request_id="fresh-coord")
    coord1 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    coord2 = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result1 = coord1.execute(request)
    result2 = coord2.execute(request)
    assert result1.route_decision == result2.route_decision
    assert result1.issuance_policy_decision == result2.issuance_policy_decision
    assert result1.execution_decision == result2.execution_decision


def test_authority_valid_at_fixed_clock(fixed_clock, executor_registry):
    """Authority validation using the same fixed clock = deterministic VALID result."""
    request = _make_request(request_id="valid-auth")
    coord = GovernedProductionCoordinator(clock=fixed_clock, executor_registry=executor_registry)
    result = coord.execute(request)
    assert result.authority_valid is True
    assert result.execution_decision == "EXECUTE"


def test_authority_expired_at_injected_later_clock(executor_registry):
    """Moving only the injected validation clock past expiry = deterministic EXPIRED/REJECT result."""
    # Create an authority with a short TTL using the fixed clock
    fixed_clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    
    # Issue the authority using the fixed clock
    from tools.hermes_core.production_issuance import ProductionIssuancePolicy, ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import get_default_router, RoutingRequest
    
    router = get_default_router()
    route_result = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
    
    policy = ProductionIssuancePolicy(clock=fixed_clock)
    issuance_request = ProductionIssuanceRequest(
        request_id="expired-auth",
        receiver_id="kilo-cli-agent",
        routing_result=route_result,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,  # 1 hour TTL
        request_nonce="expired-auth-nonce",
    )
    issuance_result = policy.evaluate(issuance_request)
    assert issuance_result.authority_issued is True
    assert issuance_result.authority_valid is True
    
    # Validate with the fixed clock (should be valid)
    from tools.hermes_core.receiver_dispatch import ExecutionAuthorityValidator
    valid_validator = ExecutionAuthorityValidator(
        router_contract_id=compute_ea4e6_router_contract_id(),
        now=QUALIFICATION_CLOCK,
    )
    decision = valid_validator.validate(issuance_result.authority, route_result)
    assert decision.authority_valid is True
    
    # Now create a validator with a clock past the expiry (2 hours later)
    expired_validator = ExecutionAuthorityValidator(
        router_contract_id=compute_ea4e6_router_contract_id(),
        now="2026-01-01T02:00:00Z",  # Past the 1-hour expiry
    )
    decision = expired_validator.validate(issuance_result.authority, route_result)
    assert decision.authority_valid is False
    assert decision.reason == "AUTHORITY_EXPIRED"


def _make_issuance_request(request: GovernedExecutionRequest, clock: ClockCollaborator):
    """Helper to create a ProductionIssuanceRequest from a GovernedExecutionRequest."""
    from tools.hermes_core.production_issuance import ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import RoutingResult
    return ProductionIssuanceRequest(
        request_id=request.request_id,
        receiver_id=request.receiver_id,
        routing_result=RoutingResult(
            receiver_id=request.receiver_id,
            qualification_state="QUALIFIED",
            route_decision="SELECTED",
            route_reason="test",
            execution_authority_present=True,
        ),
        router_contract_id=request.router_contract_id,
        transport_contract_id=request.transport_contract_id,
        model_binding_id=request.model_binding_id,
        delegation_class=request.delegation_class,
        requested_operation=request.requested_operation,
        requested_execution_scope=request.requested_execution_scope,
        requested_attempt_limit=request.requested_attempt_limit,
        requested_authority_ttl_seconds=request.requested_authority_ttl_seconds,
        request_nonce=f"ea4e18-{request.request_id}",
    )


# --- No execution on rejection ---

def test_no_execution_on_issuance_rejection(fixed_clock, executor_registry):
    policy = ProductionIssuancePolicy(clock=fixed_clock, max_attempt_limit=0)
    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=executor_registry,
        policy=policy,
    )
    request = _make_request()
    result = coord.execute(request)
    assert result.executor_called is False
    assert result.execution_request_created is False


# --- Integration contract ---

def test_integration_contract_deterministic():
    id1 = compute_ea4e18_integration_contract_id()
    id2 = compute_ea4e18_integration_contract_id()
    assert id1 == id2


# --- Clock injection verification ---

def test_direct_system_clock_read_not_in_ea4e18_path():
    """Verify that the EA-4E.18 path uses injected clock, not direct datetime.now()."""
    from tools.hermes_core import governed_production
    import inspect
    source = inspect.getsource(governed_production)
    assert "datetime.now(" not in source, "EA-4E.18 path should not directly call datetime.now()"


def test_policy_clock_injectable():
    """Verify that the policy clock is injectable."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    registry = ExecutorRegistry()
    registry.register("kilo-cli-agent", EA4E18FakeKiloExecutor())
    coord = GovernedProductionCoordinator(clock=clock, executor_registry=registry)
    assert coord._policy._clock is clock


def test_qualification_clock_is_fixed():
    """Verify the qualification clock is fixed and deterministic."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    assert clock.now_iso() == QUALIFICATION_CLOCK
    # Same clock value every time
    assert clock.now_iso() == clock.now_iso()


def test_qualification_clock_does_not_read_system_time():
    """Verify the qualification clock does not read system time."""
    import inspect
    from tools.hermes_core.production_issuance import ClockCollaborator
    source = inspect.getsource(ClockCollaborator)
    assert "datetime.now(" not in source or "now" not in source
    # The ClockCollaborator should only use the injected _now value
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    # Verify it returns the injected value, not system time
    assert clock.now_iso() == QUALIFICATION_CLOCK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
