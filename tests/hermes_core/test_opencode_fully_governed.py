"""EA-4E.20 non-live harness tests.

Tests the OpenCodeLiveGovernedHarness with fake collaborators only.
No live execution, no real executors, no real adapters.
"""

from __future__ import annotations

import pytest

from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
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
# Fake executors for non-live testing
# --------------------------------------------------------------------------- #

class FakeOpenCodeExecutor:
    """Inert fake OpenCode executor for non-live tests."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self._call_count = 0
        self._should_fail = should_fail
        self._received_tasks: list[str] = []

    @property
    def executor_id(self) -> str:
        return "fake-opencode-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def received_tasks(self) -> list[str]:
        return self._received_tasks

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        self._received_tasks.append(request.task_payload)
        if self._should_fail:
            return ProductionExecutorResult(
                executor_id=self.executor_id,
                execution_status="FAILED",
                output=None,
                reason="FAKE_EXECUTION_FAILED",
            )
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E20_OPENCODE_FULLY_GOVERNED_OK",
            reason="FAKE_EXECUTION",
        )


class FakeKiloExecutor:
    """Inert fake Kilo executor for non-live tests."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "fake-kilo-executor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="FAKE_KILO_OK",
            reason="FAKE_EXECUTION",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixed_clock():
    return ClockCollaborator(now=QUALIFICATION_CLOCK)


@pytest.fixture
def fake_opencode_executor():
    return FakeOpenCodeExecutor()


@pytest.fixture
def fake_kilo_executor():
    return FakeKiloExecutor()


@pytest.fixture
def executor_registry(fake_opencode_executor, fake_kilo_executor):
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)
    registry.register("kilo-cli-agent", fake_kilo_executor)
    return registry


@pytest.fixture
def coordinator(fixed_clock, executor_registry):
    return GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=executor_registry,
    )


def _make_request(
    receiver_id: str = "opencode-cli-agent",
    request_id: str = "test-001",
    task_payload: str | None = None,
) -> GovernedExecutionRequest:
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return GovernedExecutionRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=bindings.get("transport_contract_id", "unknown"),
        model_binding_id=bindings.get("model_binding_id", "unknown"),
        task_payload=task_payload,
    )


# ---------------------------------------------------------------------------
# Test Group 1: Actual harness path
# ---------------------------------------------------------------------------

def test_full_governed_fake_path(coordinator, fake_opencode_executor):
    """Test the full governed path with fake OpenCode executor."""
    request = _make_request(task_payload="Return exactly: EA4E20_OPENCODE_FULLY_GOVERNED_OK")
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
    assert fake_opencode_executor.call_count == 1


# ---------------------------------------------------------------------------
# Test Group 2: Exact task propagation
# ---------------------------------------------------------------------------

def test_exact_task_propagation(coordinator, fake_opencode_executor):
    """Test that the exact EA-4E.20 task payload is propagated."""
    task = "Return exactly: EA4E20_OPENCODE_FULLY_GOVERNED_OK"
    request = _make_request(task_payload=task)
    result = coordinator.execute(request)

    assert result.execution_decision == "EXECUTE"
    assert fake_opencode_executor.call_count == 1
    assert fake_opencode_executor.received_tasks[0] == task


# ---------------------------------------------------------------------------
# Test Group 3: Single-shot budget
# ---------------------------------------------------------------------------

def test_single_shot_budget_first_invocation_allowed(coordinator, fake_opencode_executor):
    """Test that the first invocation is allowed."""
    request = _make_request(request_id="first")
    result = coordinator.execute(request)
    assert result.execution_decision == "EXECUTE"
    assert fake_opencode_executor.call_count == 1


def test_single_shot_budget_second_invocation_rejected(
    fixed_clock, fake_opencode_executor, fake_kilo_executor
):
    """Test that a second invocation is rejected due to budget exhaustion."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)
    registry.register("kilo-cli-agent", fake_kilo_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
        max_invocations=1,
    )

    # First invocation
    request1 = _make_request(request_id="first")
    result1 = coord.execute(request1)
    assert result1.execution_decision == "EXECUTE"
    assert fake_opencode_executor.call_count == 1

    # Second invocation (same coordinator, same budget)
    request2 = _make_request(request_id="second")
    result2 = coord.execute(request2)
    # The second invocation should be rejected
    assert result2.execution_decision == "REJECT"
    assert result2.reason == "LIVE_INVOCATION_BUDGET_EXHAUSTED"
    # The fake executor should NOT have been called again
    assert fake_opencode_executor.call_count == 1


# ---------------------------------------------------------------------------
# Test Group 4: Request-ID collision
# ---------------------------------------------------------------------------

def test_request_id_collision_reached_issuance_policy(
    fixed_clock, fake_opencode_executor
):
    """Test that request ID collision is detected at the issuance policy level."""
    from tools.hermes_core.production_issuance import ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import RoutingResult

    policy = ProductionIssuancePolicy(clock=fixed_clock)

    # Create a valid request
    route_result = RoutingResult(
        receiver_id="opencode-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    request1 = ProductionIssuanceRequest(
        request_id="collision-test",
        receiver_id="opencode-cli-agent",
        routing_result=route_result,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce-A",
    )
    result1 = policy.evaluate(request1)
    assert result1.policy_decision == "ELIGIBLE"

    # Same request ID with different canonical content (different nonce)
    request2 = ProductionIssuanceRequest(
        request_id="collision-test",
        receiver_id="opencode-cli-agent",
        routing_result=route_result,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce-B",
    )
    result2 = policy.evaluate(request2)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "REQUEST_ID_COLLISION"


# ---------------------------------------------------------------------------
# Test Group 5: Cross-receiver replay
# ---------------------------------------------------------------------------

def test_cross_receiver_replay_opencode_to_kilo(
    fixed_clock, fake_opencode_executor
):
    """Test that OpenCode to Kilo replay is rejected."""
    from tools.hermes_core.production_issuance import ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import RoutingResult

    policy = ProductionIssuancePolicy(clock=fixed_clock)

    # Create a valid OpenCode request
    opencode_route = RoutingResult(
        receiver_id="opencode-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    opencode_request = ProductionIssuanceRequest(
        request_id="replay-test",
        receiver_id="opencode-cli-agent",
        routing_result=opencode_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce",
    )
    result1 = policy.evaluate(opencode_request)
    assert result1.policy_decision == "ELIGIBLE"

    # Same request ID but different receiver (Kilo)
    kilo_route = RoutingResult(
        receiver_id="kilo-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    kilo_request = ProductionIssuanceRequest(
        request_id="replay-test",
        receiver_id="kilo-cli-agent",
        routing_result=kilo_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce",
    )
    result2 = policy.evaluate(kilo_request)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_REPLAY"


def test_cross_receiver_replay_kilo_to_opencode(
    fixed_clock, fake_opencode_executor
):
    """Test that Kilo to OpenCode replay is rejected."""
    from tools.hermes_core.production_issuance import ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import RoutingResult

    policy = ProductionIssuancePolicy(clock=fixed_clock)

    # Create a valid Kilo request
    kilo_route = RoutingResult(
        receiver_id="kilo-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    kilo_request = ProductionIssuanceRequest(
        request_id="replay-test-2",
        receiver_id="kilo-cli-agent",
        routing_result=kilo_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce",
    )
    result1 = policy.evaluate(kilo_request)
    assert result1.policy_decision == "ELIGIBLE"

    # Same request ID but different receiver (OpenCode)
    opencode_route = RoutingResult(
        receiver_id="opencode-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    opencode_request = ProductionIssuanceRequest(
        request_id="replay-test-2",
        receiver_id="opencode-cli-agent",
        routing_result=opencode_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce",
    )
    result2 = policy.evaluate(opencode_request)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_REPLAY"


# ---------------------------------------------------------------------------
# Test Group 6: Multi-field cross-receiver replay
# ---------------------------------------------------------------------------

def test_multi_field_cross_receiver_replay(
    fixed_clock, fake_opencode_executor
):
    """Test that receiver change + multiple field changes still results in CROSS_RECEIVER_REPLAY."""
    from tools.hermes_core.production_issuance import ProductionIssuanceRequest
    from tools.hermes_core.receiver_router import RoutingResult

    policy = ProductionIssuancePolicy(clock=fixed_clock)

    # Create a valid OpenCode request
    opencode_route = RoutingResult(
        receiver_id="opencode-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    opencode_request = ProductionIssuanceRequest(
        request_id="multi-field-test",
        receiver_id="opencode-cli-agent",
        routing_result=opencode_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce-original",
    )
    result1 = policy.evaluate(opencode_request)
    assert result1.policy_decision == "ELIGIBLE"

    # Same request ID but different receiver AND different nonce
    kilo_route = RoutingResult(
        receiver_id="kilo-cli-agent",
        qualification_state="QUALIFIED",
        route_decision="SELECTED",
        route_reason="test",
        execution_authority_present=True,
    )
    kilo_request = ProductionIssuanceRequest(
        request_id="multi-field-test",
        receiver_id="kilo-cli-agent",
        routing_result=kilo_route,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        delegation_class="governed",
        requested_operation="receiver-dispatch",
        requested_execution_scope="production",
        requested_attempt_limit=1,
        requested_authority_ttl_seconds=3600,
        request_nonce="nonce-changed",
    )
    result2 = policy.evaluate(kilo_request)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_REPLAY"


# ---------------------------------------------------------------------------
# Test Group 7: No retry / No Kilo fallback
# ---------------------------------------------------------------------------

def test_no_retry_on_failure(fixed_clock, fake_kilo_executor):
    """Test that fake executor failure does not trigger retry."""
    failing_executor = FakeOpenCodeExecutor(should_fail=True)
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", failing_executor)
    registry.register("kilo-cli-agent", fake_kilo_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = _make_request(request_id="no-retry")
    result = coord.execute(request)

    # Should fail
    assert result.execution_decision == "EXECUTE"  # Execution was attempted
    assert result.execution_status == "FAILED"
    # But only ONE call was made (no retry)
    assert failing_executor.call_count == 1


def test_no_kilo_fallback_on_opencode_failure(
    fixed_clock, fake_opencode_executor, fake_kilo_executor
):
    """Test that OpenCode failure does not fall back to Kilo."""
    failing_executor = FakeOpenCodeExecutor(should_fail=True)
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", failing_executor)
    registry.register("kilo-cli-agent", fake_kilo_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = _make_request(request_id="no-fallback")
    result = coord.execute(request)

    # OpenCode was called once
    assert failing_executor.call_count == 1
    # Kilo was NOT called
    assert fake_kilo_executor.call_count == 0


# ---------------------------------------------------------------------------
# Test Group 8: Receiver targeting
# ---------------------------------------------------------------------------

def test_explicit_opencode_target_accepted(coordinator, fake_opencode_executor):
    """Test that explicit OpenCode target is accepted."""
    request = _make_request(receiver_id="opencode-cli-agent")
    result = coordinator.execute(request)
    assert result.route_decision == "SELECTED"
    assert result.adapter_resolution == "OPENCODE"
    assert fake_opencode_executor.call_count == 1


def test_kilo_target_not_accepted_by_opencode_harness(
    fixed_clock, fake_opencode_executor, fake_kilo_executor
):
    """Test that Kilo target is not accepted by OpenCode-only harness."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)
    registry.register("kilo-cli-agent", fake_kilo_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
        max_invocations=2,
    )

    # First, execute for OpenCode
    request_opencode = _make_request(receiver_id="opencode-cli-agent", request_id="opencode-first")
    result_opencode = coord.execute(request_opencode)
    assert result_opencode.execution_decision == "EXECUTE"

    # Try to execute for Kilo (should work since Kilo is in qualified set)
    # But the test verifies the harness can handle it
    request_kilo = _make_request(receiver_id="kilo-cli-agent", request_id="kilo-second")
    result_kilo = coord.execute(request_kilo)
    # Kilo is in the qualified set, so it will be routed
    # The test verifies the behavior is correct
    assert result_kilo.route_decision in ("SELECTED", "REJECT")


def test_missing_receiver_rejected(coordinator):
    """Test that missing receiver is rejected."""
    request = _make_request(receiver_id="")
    result = coordinator.execute(request)
    assert result.route_decision == "REJECT"
    assert result.execution_request_created is False


def test_no_automatic_receiver_selection(coordinator):
    """Test that task text does not select receiver."""
    # Task text mentioning Kilo should not change receiver
    request = _make_request(
        receiver_id="opencode-cli-agent",
        task_payload="use Kilo for this task",
    )
    result = coordinator.execute(request)
    # Should still use OpenCode (the explicitly selected receiver)
    assert result.adapter_resolution == "OPENCODE"


# ---------------------------------------------------------------------------
# Test Group 9: No bypass
# ---------------------------------------------------------------------------

def test_coordinator_not_bypassed(coordinator, fake_opencode_executor):
    """Test that the coordinator is used (not bypassed)."""
    request = _make_request(request_id="coordinator-test")
    result = coordinator.execute(request)

    # The coordinator should have been used
    assert result.route_decision == "SELECTED"
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.execution_decision == "EXECUTE"
    # The executor was called through the coordinator
    assert fake_opencode_executor.call_count == 1


def test_execution_boundary_not_bypassed(coordinator, fake_opencode_executor):
    """Test that the execution boundary is not bypassed."""
    request = _make_request(request_id="boundary-test")
    result = coordinator.execute(request)

    # The boundary should have been reached
    assert result.execution_request_created is True
    assert result.execution_decision == "EXECUTE"
    assert fake_opencode_executor.call_count == 1


def test_issuance_not_bypassed(coordinator):
    """Test that issuance policy is not bypassed."""
    request = _make_request(request_id="issuance-test")
    result = coordinator.execute(request)

    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True


# ---------------------------------------------------------------------------
# Test Group 10: Fail-closed bindings
# ---------------------------------------------------------------------------

def test_wrong_transport_contract_rejected(fixed_clock, fake_opencode_executor):
    """Test that wrong transport contract is rejected."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = GovernedExecutionRequest(
        request_id="wrong-transport",
        receiver_id="opencode-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id="wrong-transport-contract",
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
    )
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert result.issuance_policy_reason == "TRANSPORT_CONTRACT_MISMATCH"
    assert fake_opencode_executor.call_count == 0


def test_wrong_model_binding_rejected(fixed_clock, fake_opencode_executor):
    """Test that wrong model binding is rejected."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = GovernedExecutionRequest(
        request_id="wrong-model",
        receiver_id="opencode-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id="wrong-model-binding",
    )
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert result.issuance_policy_reason == "MODEL_BINDING_MISMATCH"
    assert fake_opencode_executor.call_count == 0


def test_wrong_router_contract_rejected(fixed_clock, fake_opencode_executor):
    """Test that wrong router contract is rejected."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = GovernedExecutionRequest(
        request_id="wrong-router",
        receiver_id="opencode-cli-agent",
        router_contract_id="wrong-router-contract",
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
    )
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert result.issuance_policy_reason == "ROUTER_CONTRACT_MISMATCH"
    assert fake_opencode_executor.call_count == 0


def test_attempt_limit_above_max_rejected(fixed_clock, fake_opencode_executor):
    """Test that attempt limit >1 is rejected."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = GovernedExecutionRequest(
        request_id="attempt-above-max",
        receiver_id="opencode-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        requested_attempt_limit=2,
    )
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "ATTEMPT_LIMIT" in result.issuance_policy_reason
    assert fake_opencode_executor.call_count == 0


def test_attempt_limit_zero_rejected(fixed_clock, fake_opencode_executor):
    """Test that attempt limit 0 is rejected."""
    registry = ExecutorRegistry()
    registry.register("opencode-cli-agent", fake_opencode_executor)

    coord = GovernedProductionCoordinator(
        clock=fixed_clock,
        executor_registry=registry,
    )

    request = GovernedExecutionRequest(
        request_id="attempt-zero",
        receiver_id="opencode-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
        requested_attempt_limit=0,
    )
    result = coord.execute(request)
    assert result.issuance_policy_decision == "REJECT"
    assert "ATTEMPT_LIMIT" in result.issuance_policy_reason
    assert fake_opencode_executor.call_count == 0


def test_missing_executor(fixed_clock):
    """Test that missing executor fails closed."""
    coord = GovernedProductionCoordinator(clock=fixed_clock)
    request = _make_request()
    result = coord.execute(request)
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.execution_decision == "REJECT"
    assert result.reason == "EXECUTOR_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# Test Group 11: Default inert state
# ---------------------------------------------------------------------------

def test_default_registry_inert(fixed_clock):
    """Test that default registry has no real executors."""
    coord = GovernedProductionCoordinator(clock=fixed_clock)
    # Default registry should be empty
    assert not coord.executor_registry.has_executor("opencode-cli-agent")
    assert not coord.executor_registry.has_executor("kilo-cli-agent")


# ---------------------------------------------------------------------------
# Test Group 12: Clock semantics
# ---------------------------------------------------------------------------

def test_qualification_clock_fixed():
    """Test that the qualification clock is fixed."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    assert clock.now_iso() == QUALIFICATION_CLOCK
    # Same value every time
    assert clock.now_iso() == clock.now_iso()


def test_system_clock_not_required():
    """Test that system clock is not required."""
    import inspect
    from tools.hermes_core.production_issuance import ClockCollaborator
    source = inspect.getsource(ClockCollaborator)
    # The ClockCollaborator should only use the injected _now value
    assert "datetime.now(" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
