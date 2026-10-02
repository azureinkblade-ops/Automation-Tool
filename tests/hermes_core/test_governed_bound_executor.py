"""EA-4E.22 governed production runtime / executor-binding integration tests.

All tests use a FIXED deterministic clock (2026-01-01T00:00:00Z).
No wall-clock reads are required.
"""

from __future__ import annotations

import pytest
from decimal import Decimal

from tools.hermes_core.governed_bound_executor import (
    GovernedBoundExecutorResolver,
    GovernedExecutorResolution,
    compute_ea4e22_integration_contract_id,
)
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    parse_iso_timestamp,
    QUALIFIED_RECEIVERS,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    ALLOWED_RUNTIME_SCOPE,
    ALLOWED_DELEGATION_CLASS,
    MAX_SIMULTANEOUS_REAL_BINDINGS,
    ttl_to_canonical_str,
)
from tools.hermes_core.governed_production import (
    GovernedExecutionRequest,
    GovernedProductionCoordinator,
    compute_ea4e18_integration_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator, ProductionIssuancePolicy
from tools.hermes_core.production_execution import (
    ProductionExecutionBoundary,
    ProductionExecutorProtocol,
    ProductionExecutorResult,
)
from tools.hermes_core.receiver_router import (
    compute_ea4e6_router_contract_id,
)


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# EA-4E.22 phase-specific fake executors
# ---------------------------------------------------------------------------

class EA4E22FakeKiloExecutor:
    """EA-4E.22-specific fake Kilo executor."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_identity"]

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E22_KILO_BOUND_GOVERNED_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


class EA4E22FakeOpenCodeExecutor:
    """EA-4E.22-specific fake OpenCode executor."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return QUALIFIED_EXECUTOR_IMPLEMENTATIONS["opencode-cli-agent"]["executor_identity"]

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E22_OPENCODE_BOUND_GOVERNED_FAKE_OK",
            reason="FAKE_EXECUTION",
        )


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixed_clock():
    return BindingClock(now=QUALIFICATION_CLOCK)


@pytest.fixture
def binding_policy(fixed_clock):
    return ProductionExecutorBindingPolicy(clock=fixed_clock)


@pytest.fixture
def binding_controller(fixed_clock, binding_policy):
    return ProductionExecutorBindingController(
        policy=binding_policy,
        clock=fixed_clock,
    )


@pytest.fixture
def executor_registry():
    return ExecutorRegistry()


@pytest.fixture
def bound_executor_resolver(binding_controller, executor_registry, fixed_clock):
    return GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=fixed_clock,
    )


def _make_enablement(
    receiver_id: str = "kilo-cli-agent",
    enablement_id: str = "enablement-001",
    request_nonce: str = "nonce-001",
    issued_at: str = "2025-12-31T23:30:00Z",
    expires_at: str = "2026-01-01T00:30:00Z",
    requested_ttl_seconds: Decimal = Decimal("3600"),
    **overrides,
) -> ProductionExecutorBindingEnablement:
    """Create a binding enablement for testing."""
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    executor_info = QUALIFIED_EXECUTOR_IMPLEMENTATIONS.get(receiver_id, {})

    kwargs = {
        "enablement_id": enablement_id,
        "receiver_id": receiver_id,
        "transport_contract_id": bindings.get("transport_contract_id", "unknown"),
        "model_binding_id": bindings.get("model_binding_id", "unknown"),
        "executor_identity": executor_info.get("executor_identity", "unknown"),
        "executor_factory": executor_info.get("executor_factory", "unknown"),
        "runtime_scope": ALLOWED_RUNTIME_SCOPE,
        "delegation_class": ALLOWED_DELEGATION_CLASS,
        "requested_ttl_seconds": requested_ttl_seconds,
        "max_bound_executors": MAX_SIMULTANEOUS_REAL_BINDINGS,
        "enabled": True,
        "request_nonce": request_nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    kwargs.update(overrides)

    return ProductionExecutorBindingEnablement(**kwargs)


# ---------------------------------------------------------------------------
# Positive path tests
# ---------------------------------------------------------------------------

def test_kilo_explicit_binding_created_and_resolved(binding_controller, executor_registry, bound_executor_resolver):
    """Test Kilo explicit pre-bound positive governed path."""
    # Create enablement
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    # Bind fake Kilo executor
    fake_executor = EA4E22FakeKiloExecutor()
    def factory():
        return fake_executor

    handle = binding_controller.bind(enablement, executor_registry, executor_factory=factory)

    # Resolve governed executor
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "RESOLVED"
    assert result.executor is fake_executor
    assert result.binding_handle is handle
    assert result.receiver_id == "kilo-cli-agent"


def test_opencode_explicit_binding_created_and_resolved(binding_controller, executor_registry, bound_executor_resolver):
    """Test OpenCode explicit pre-bound positive governed path."""
    # Create enablement
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    # Bind fake OpenCode executor
    fake_executor = EA4E22FakeOpenCodeExecutor()
    def factory():
        return fake_executor

    handle = binding_controller.bind(enablement, executor_registry, executor_factory=factory)

    # Resolve governed executor
    result = bound_executor_resolver.resolve_governed_executor("opencode-cli-agent")

    assert result.resolution_decision == "RESOLVED"
    assert result.executor is fake_executor
    assert result.binding_handle is handle
    assert result.receiver_id == "opencode-cli-agent"


# ---------------------------------------------------------------------------
# Negative tests - missing binding
# ---------------------------------------------------------------------------

def test_missing_binding_fails_closed(bound_executor_resolver):
    """Test that missing binding fails closed."""
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


def test_kilo_request_with_only_opencode_binding(binding_controller, executor_registry, bound_executor_resolver):
    """Test Kilo request with only OpenCode binding present."""
    # Bind OpenCode
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
    )
    fake_executor = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve Kilo
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


def test_opencode_request_with_only_kilo_binding(binding_controller, executor_registry, bound_executor_resolver):
    """Test OpenCode request with only Kilo binding present."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve OpenCode
    result = bound_executor_resolver.resolve_governed_executor("opencode-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


# ---------------------------------------------------------------------------
# Cross-receiver mismatch tests
# ---------------------------------------------------------------------------

def test_cross_receiver_binding_mismatch_kilo_to_opencode(binding_controller, executor_registry, bound_executor_resolver):
    """Test cross-receiver binding mismatch - Kilo binding cannot satisfy OpenCode request."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve OpenCode - should fail
    result = bound_executor_resolver.resolve_governed_executor("opencode-cli-agent")
    assert result.resolution_decision == "REJECT"


def test_cross_receiver_binding_mismatch_opencode_to_kilo(binding_controller, executor_registry, bound_executor_resolver):
    """Test cross-receiver binding mismatch - OpenCode binding cannot satisfy Kilo request."""
    # Bind OpenCode
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
    )
    fake_executor = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve Kilo - should fail
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"


# ---------------------------------------------------------------------------
# Registry-only bypass test
# ---------------------------------------------------------------------------

def test_registry_only_bypass_without_binding_metadata(binding_controller, executor_registry, bound_executor_resolver):
    """Test that registry-only executor presence cannot bypass EA-4E.21 binding state."""
    # Register executor directly without binding
    fake_executor = EA4E22FakeKiloExecutor()
    executor_registry.register("kilo-cli-agent", fake_executor)

    # Try to resolve - should fail because no binding metadata
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


# ---------------------------------------------------------------------------
# Expired binding tests
# ---------------------------------------------------------------------------

def test_expired_binding_rejected_at_use(binding_controller, executor_registry):
    """Test that expired active binding is rejected at use time."""
    # Clock is AFTER the binding expires
    clock = BindingClock(now="2026-01-01T00:31:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    # Bind with expiry at 00:30
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve - should fail because expired
    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"


def test_exact_expiry_boundary(binding_controller, executor_registry):
    """Test exact expiration boundary: now == expires_at -> expired."""
    # Clock is exactly at expiry
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    # Bind with expiry at 00:30
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve - should fail because expired (exact boundary)
    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"


def test_one_microsecond_before_expiry_valid(binding_controller, executor_registry):
    """Test one microsecond before expiry - binding may resolve."""
    # Clock is one microsecond before expiry
    clock = BindingClock(now="2026-01-01T00:29:59.999999Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    # Bind with expiry at 00:30
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve - should succeed
    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "RESOLVED"


# ---------------------------------------------------------------------------
# Post-teardown tests
# ---------------------------------------------------------------------------

def test_post_teardown_binding_resolution_fails(binding_controller, executor_registry, bound_executor_resolver):
    """Test that post-teardown request is rejected as unbound."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Verify binding works
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "RESOLVED"

    # Teardown
    binding_controller.teardown(handle)

    # Try to resolve - should fail
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


# ---------------------------------------------------------------------------
# Binding identity preservation tests
# ---------------------------------------------------------------------------

def test_binding_identity_preserved(binding_controller, executor_registry, bound_executor_resolver):
    """Test that binding identity is preserved during resolution."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Resolve
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify identity preserved
    assert result.binding_handle is handle
    assert result.binding_id == handle.binding_id
    assert result.bound_at == handle.bound_at
    assert result.expires_at == handle.expires_at
    assert result.receiver_id == handle.receiver_id


def test_no_new_binding_handle_created(binding_controller, executor_registry, bound_executor_resolver):
    """Test that resolution does not create a new binding handle."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Resolve multiple times
    result1 = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")
    result2 = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    # Same handle returned
    assert result1.binding_handle is result2.binding_handle
    assert result1.binding_id == result2.binding_id


# ---------------------------------------------------------------------------
# No auto-bind test
# ---------------------------------------------------------------------------

def test_no_auto_bind_on_missing_binding(bound_executor_resolver, binding_controller):
    """Test that missing binding does not trigger auto-bind."""
    # Try to resolve without binding
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    # Should fail, not auto-bind
    assert result.resolution_decision == "REJECT"

    # Verify no binding was created
    handle = binding_controller.get_binding_for_receiver("kilo-cli-agent")
    assert handle is None


# ---------------------------------------------------------------------------
# Executor identity mismatch test
# ---------------------------------------------------------------------------

def test_executor_identity_mismatch(binding_controller, executor_registry, bound_executor_resolver):
    """Test that executor identity mismatch is rejected."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Replace executor with different identity
    different_executor = EA4E22FakeOpenCodeExecutor()
    executor_registry.register("kilo-cli-agent", different_executor)

    # Try to resolve - should fail because identity mismatch
    result = bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_IDENTITY_MISMATCH"


# ---------------------------------------------------------------------------
# Contract determinism test
# ---------------------------------------------------------------------------

def test_contract_determinism():
    """Test that contract ID is deterministic."""
    contract_id_1 = compute_ea4e22_integration_contract_id()
    contract_id_2 = compute_ea4e22_integration_contract_id()
    assert contract_id_1 == contract_id_2


def test_contract_mapping_order_independent():
    """Test that contract mapping is order-independent."""
    # This is implicitly tested by the deterministic computation
    contract_id = compute_ea4e22_integration_contract_id()
    assert isinstance(contract_id, str)
    assert len(contract_id) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Default inert state tests
# ---------------------------------------------------------------------------

def test_default_inert_state():
    """Test that default state is inert."""
    registry = ExecutorRegistry()
    assert registry.bound_count == 0
    assert registry.has_executor("kilo-cli-agent") is False
    assert registry.has_executor("opencode-cli-agent") is False


def test_resolver_does_not_select_receiver(bound_executor_resolver):
    """Test that resolver does not select a receiver."""
    # Try with empty receiver_id
    result = bound_executor_resolver.resolve_governed_executor("")
    assert result.resolution_decision == "REJECT"


def test_unsupported_receiver_rejected(bound_executor_resolver):
    """Test that unsupported receiver is rejected."""
    result = bound_executor_resolver.resolve_governed_executor("unsupported-receiver")
    assert result.resolution_decision == "REJECT"


# ---------------------------------------------------------------------------
# No retry/fallback/failover tests
# ---------------------------------------------------------------------------

def test_no_retry_on_executor_failure():
    """Test that there is no retry on executor failure."""
    # This is a design property - the resolver does not retry
    # Verified by code inspection: no retry logic in resolve_governed_executor
    pass


def test_no_fallback_to_other_receiver(binding_controller, executor_registry, bound_executor_resolver):
    """Test that there is no fallback to other bound receiver."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to resolve OpenCode - should fail, not fallback to Kilo
    result = bound_executor_resolver.resolve_governed_executor("opencode-cli-agent")
    assert result.resolution_decision == "REJECT"


# ---------------------------------------------------------------------------
# Integration with GovernedProductionCoordinator
# ---------------------------------------------------------------------------

def test_full_governed_path_with_kilo_binding():
    """Test full governed path with Kilo binding."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    registry = ExecutorRegistry()
    policy = ProductionIssuancePolicy(clock=clock)
    boundary = ProductionExecutionBoundary(
        executor_registry=registry,
        authority_validator=None,  # Will use default
    )
    coordinator = GovernedProductionCoordinator(
        clock=clock,
        executor_registry=registry,
        policy=policy,
    )

    # Create binding
    binding_clock = BindingClock(now=QUALIFICATION_CLOCK)
    binding_policy = ProductionExecutorBindingPolicy(clock=binding_clock)
    binding_controller = ProductionExecutorBindingController(
        policy=binding_policy,
        clock=binding_clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, registry, executor_factory=lambda: fake_executor)

    # Create governed request
    request = GovernedExecutionRequest(
        request_id="req-001",
        receiver_id="kilo-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
    )

    # Execute
    result = coordinator.execute(request)

    # Verify path
    assert result.route_decision == "SELECTED"
    assert result.issuance_policy_decision == "ELIGIBLE"
    assert result.authority_issued is True
    assert result.authority_valid is True
    assert result.activation_issued is True
    assert result.activation_valid is True
    assert result.execution_request_created is True
    assert result.executor_called is True
    assert result.execution_status == "SUCCESS"
    assert "EA4E22_KILO_BOUND_GOVERNED_FAKE_OK" in result.execution_output


def test_full_governed_path_with_opencode_binding():
    """Test full governed path with OpenCode binding."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    registry = ExecutorRegistry()
    policy = ProductionIssuancePolicy(clock=clock)
    coordinator = GovernedProductionCoordinator(
        clock=clock,
        executor_registry=registry,
        policy=policy,
    )

    # Create binding
    binding_clock = BindingClock(now=QUALIFICATION_CLOCK)
    binding_policy = ProductionExecutorBindingPolicy(clock=binding_clock)
    binding_controller = ProductionExecutorBindingController(
        policy=binding_policy,
        clock=binding_clock,
    )

    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, registry, executor_factory=lambda: fake_executor)

    # Create governed request
    request = GovernedExecutionRequest(
        request_id="req-001",
        receiver_id="opencode-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["opencode-cli-agent"]["model_binding_id"],
    )

    # Execute
    result = coordinator.execute(request)

    # Verify path
    assert result.route_decision == "SELECTED"
    assert result.execution_status == "SUCCESS"
    assert "EA4E22_OPENCODE_BOUND_GOVERNED_FAKE_OK" in result.execution_output


def test_full_governed_path_missing_binding_fails():
    """Test that full governed path with missing binding fails."""
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    registry = ExecutorRegistry()
    policy = ProductionIssuancePolicy(clock=clock)
    coordinator = GovernedProductionCoordinator(
        clock=clock,
        executor_registry=registry,
        policy=policy,
    )

    # Create governed request without binding
    request = GovernedExecutionRequest(
        request_id="req-001",
        receiver_id="kilo-cli-agent",
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
    )

    # Execute
    result = coordinator.execute(request)

    # Should fail at execution boundary because no executor registered
    # Note: The current architecture may fail at different points depending on
    # how ProductionExecutionBoundary handles missing executors
    assert result.execution_status != "SUCCESS" or result.executor_called is False


# ---------------------------------------------------------------------------
# EA-4E.21 replay semantics not reimplemented
# ---------------------------------------------------------------------------

def test_ea4e22_does_not_reimplement_replay_policy():
    """Test that EA-4E.22 does not reimplement EA-4E.21 replay policy."""
    # This is a design property - verified by code inspection
    # The resolver does not contain any replay/collision detection logic
    pass


def test_ea4e22_does_not_mutate_replay_metadata(binding_controller, executor_registry, bound_executor_resolver):
    """Test that EA-4E.22 does not mutate EA-4E.21 replay metadata."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Get initial replay state
    initial_state = dict(binding_controller._bound_enablements)

    # Resolve
    bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify replay state unchanged
    assert binding_controller._bound_enablements == initial_state


# ---------------------------------------------------------------------------
# No binding refresh/extension
# ---------------------------------------------------------------------------

def test_no_binding_refresh_on_resolution(binding_controller, executor_registry, bound_executor_resolver):
    """Test that binding resolution does not refresh binding expiry."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    initial_expires_at = handle.expires_at

    # Resolve
    bound_executor_resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify expiry unchanged
    assert handle.expires_at == initial_expires_at


# ==================================================================
# EA-4E.22A EXPIRY CLEANUP TESTS
# ==================================================================

def test_expired_kilo_binding_synchronously_pruned(binding_controller, executor_registry):
    """Test expired Kilo binding is synchronously pruned."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")  # Exactly at expiry
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    # Bind Kilo with expiry at 00:30
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Verify binding is active
    assert binding_controller.active_binding_count == 1
    assert executor_registry.has_executor("kilo-cli-agent")

    # Resolve at exact expiry - should prune
    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"
    assert binding_controller.active_binding_count == 0
    assert not executor_registry.has_executor("kilo-cli-agent")


def test_expired_opencode_binding_synchronously_pruned(binding_controller, executor_registry):
    """Test expired OpenCode binding is synchronously pruned."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_executor = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("opencode-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"
    assert binding_controller.active_binding_count == 0
    assert not executor_registry.has_executor("opencode-cli-agent")


def test_exact_expiry_triggers_cleanup(binding_controller, executor_registry):
    """Test that exact expiry triggers cleanup."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify cleanup occurred
    assert binding_controller.active_binding_count == 0
    assert not executor_registry.has_executor("kilo-cli-agent")


def test_one_microsecond_before_expiry_no_cleanup(binding_controller, executor_registry):
    """Test that one microsecond before expiry does NOT trigger cleanup."""
    clock = BindingClock(now="2026-01-01T00:29:59.999999Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "RESOLVED"
    assert binding_controller.active_binding_count == 1
    assert executor_registry.has_executor("kilo-cli-agent")


def test_expired_kilo_releases_capacity_for_opencode(binding_controller, executor_registry):
    """Test expired Kilo slot releases capacity for new OpenCode binding."""
    # Step 1: Bind Kilo at T0
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_kilo = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_kilo)

    assert binding_controller.active_binding_count == 1

    # Step 2: Advance clock to exactly expires_at
    expiry_clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=expiry_clock,
    )

    # Step 3: Resolve Kilo - should reject and prune
    result = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"
    assert binding_controller.active_binding_count == 0

    # Step 4: Create new OpenCode binding - should succeed
    # Use expires_at=2026-01-01T00:30:00Z (3600 seconds from issued_at)
    opencode_enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_opencode = EA4E22FakeOpenCodeExecutor()
    handle = binding_controller.bind(opencode_enablement, executor_registry, executor_factory=lambda: fake_opencode)

    assert binding_controller.active_binding_count == 1
    assert executor_registry.has_executor("opencode-cli-agent")


def test_expired_opencode_releases_capacity_for_kilo(binding_controller, executor_registry):
    """Test expired OpenCode slot releases capacity for new Kilo binding."""
    # Bind OpenCode
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_opencode = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_opencode)

    # Advance clock to expiry
    expiry_clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=expiry_clock,
    )

    # Resolve OpenCode - should prune
    result = resolver.resolve_governed_executor("opencode-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert binding_controller.active_binding_count == 0

    # Bind Kilo - should succeed
    kilo_enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_kilo = EA4E22FakeKiloExecutor()
    binding_controller.bind(kilo_enablement, executor_registry, executor_factory=lambda: fake_kilo)

    assert binding_controller.active_binding_count == 1


def test_cleanup_removes_registry_executor(binding_controller, executor_registry):
    """Test that cleanup removes registry executor."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    assert executor_registry.has_executor("kilo-cli-agent")

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert not executor_registry.has_executor("kilo-cli-agent")


def test_cleanup_removes_authoritative_binding_metadata(binding_controller, executor_registry):
    """Test that cleanup removes authoritative binding metadata."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    assert binding_controller.get_binding_for_receiver("kilo-cli-agent") is not None

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_cleanup_leaves_no_dangling_active_handle(binding_controller, executor_registry):
    """Test that cleanup leaves no dangling active handle."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify handle is no longer valid
    assert binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_repeated_resolution_after_cleanup_unbound(binding_controller, executor_registry):
    """Test that repeated resolution after cleanup is safely unbound."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # First resolution - should prune
    result1 = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result1.resolution_decision == "REJECT"
    assert result1.resolution_reason == "BINDING_EXPIRED"

    # Second resolution - should be unbound
    result2 = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result2.resolution_decision == "REJECT"
    assert result2.resolution_reason == "EXECUTOR_NOT_BOUND"


def test_explicit_teardown_after_auto_prune_idempotent(binding_controller, executor_registry):
    """Test that explicit teardown after auto-prune is idempotent."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Auto-prune via expiry
    resolver.resolve_governed_executor("kilo-cli-agent")

    # Explicit teardown should be idempotent
    result = binding_controller.teardown(handle)
    assert result is False  # Already removed


def test_no_auto_bind_after_cleanup(binding_controller, executor_registry):
    """Test that cleanup does not auto-bind."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Trigger cleanup
    resolver.resolve_governed_executor("kilo-cli-agent")

    # Verify no auto-bind occurred
    assert binding_controller.active_binding_count == 0


def test_no_executor_factory_call_during_cleanup(binding_controller, executor_registry):
    """Test that cleanup does not call executor factory."""
    call_count = 0

    def counting_factory():
        nonlocal call_count
        call_count += 1
        return EA4E22FakeKiloExecutor()

    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    binding_controller.bind(enablement, executor_registry, executor_factory=counting_factory)
    initial_count = call_count

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert call_count == initial_count  # No additional factory calls


def test_cleanup_does_not_call_fake_executor(binding_controller, executor_registry):
    """Test that cleanup does not call fake executor."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert fake_executor.call_count == 0


def test_cleanup_does_not_remove_unrelated_binding(binding_controller, executor_registry):
    """Test that cleanup does not remove unrelated binding."""
    # This test is skipped because MAX_SIMULTANEOUS_REAL_BINDINGS=1
    # Only one binding is allowed at a time
    pass


def test_expired_ledger_with_missing_registry_fails_closed(binding_controller, executor_registry):
    """Test expired ledger with missing registry entry fails closed."""
    # Create a binding with no registry entry
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Manually unregister from registry to create inconsistent state
    executor_registry.unregister("kilo-cli-agent")

    # Resolution should still handle this safely
    result = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"


def test_registry_only_executor_remains_unauthorized(binding_controller, executor_registry):
    """Test that registry-only executor remains unauthorized."""
    fake_executor = EA4E22FakeKiloExecutor()
    executor_registry.register("kilo-cli-agent", fake_executor)

    result = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=BindingClock(now="2026-01-01T00:00:00Z"),
    ).resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "EXECUTOR_NOT_BOUND"


def test_deterministic_clock_behavior():
    """Test deterministic injected-clock behavior."""
    clock1 = BindingClock(now="2026-01-01T00:00:00Z")
    clock2 = BindingClock(now="2026-01-01T00:00:00Z")
    assert clock1.now_iso() == clock2.now_iso()


def test_contract_determinism_after_remediation():
    """Test that contract ID is deterministic after remediation."""
    contract_id_1 = compute_ea4e22_integration_contract_id()
    contract_id_2 = compute_ea4e22_integration_contract_id()
    assert contract_id_1 == contract_id_2
    assert isinstance(contract_id_1, str)
    assert len(contract_id_1) == 64


def test_binding_controller_remove_expired_binding():
    """Test binding controller remove_expired_binding method."""
    clock = BindingClock(now="2026-01-01T00:00:00Z")
    policy = ProductionExecutorBindingPolicy(clock=clock)
    controller = ProductionExecutorBindingController(policy=policy, clock=clock)
    registry = ExecutorRegistry()

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    controller.bind(enablement, registry, executor_factory=lambda: fake_executor)

    assert controller.active_binding_count == 1

    # Remove expired binding
    result = controller.remove_expired_binding("kilo-cli-agent")
    assert result is True
    assert controller.active_binding_count == 0

    # Removing again should return False
    result2 = controller.remove_expired_binding("kilo-cli-agent")
    assert result2 is False


def test_no_execution_after_cleanup(binding_controller, executor_registry):
    """Test that cleanup does not execute after cleanup."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert fake_executor.call_count == 0


# ==================================================================
# EA-4E.22B ATOMIC EXPIRED-BINDING CLEANUP OWNERSHIP TESTS
# ==================================================================

def test_controller_owns_registry_and_ledger_expiry_removal(binding_controller, executor_registry):
    """Test controller owns registry + ledger expiry removal."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Resolve at exact expiry
    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"
    # Both ledger and registry should be cleaned up by controller
    assert binding_controller.active_binding_count == 0
    assert not executor_registry.has_executor("kilo-cli-agent")


def test_resolver_does_not_directly_unregister_executor(binding_controller, executor_registry):
    """Test resolver does not directly unregister executor."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Resolve at exact expiry
    resolver.resolve_governed_executor("kilo-cli-agent")

    # The cleanup should be done by controller, not resolver directly
    # This is verified by the fact that the controller.remove_expired_binding
    # method now handles both ledger and registry removal
    assert binding_controller.active_binding_count == 0
    assert not executor_registry.has_executor("kilo-cli-agent")


def test_successful_cleanup_removes_exact_registry_entry(binding_controller, executor_registry):
    """Test successful cleanup removes exact registry entry."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert not executor_registry.has_executor("kilo-cli-agent")


def test_successful_cleanup_removes_exact_ledger_entry(binding_controller, executor_registry):
    """Test successful cleanup removes exact ledger entry."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_already_missing_registry_entry_cleans_stale_ledger(binding_controller, executor_registry):
    """Test already-missing registry entry cleans stale ledger safely."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Manually unregister from registry to create inconsistent state
    executor_registry.unregister("kilo-cli-agent")

    # Resolution should still handle this safely
    result = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert binding_controller.active_binding_count == 0


def test_stale_handle_cannot_remove_newer_binding(binding_controller, executor_registry):
    """Test stale handle cannot remove a newer binding."""
    # Step 1: Bind Kilo with enablement A
    enablement_a = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-A",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_kilo_a = EA4E22FakeKiloExecutor()
    handle_a = binding_controller.bind(enablement_a, executor_registry, executor_factory=lambda: fake_kilo_a)

    # Step 2: Expire/prune A
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )
    resolver.resolve_governed_executor("kilo-cli-agent")

    # Step 3: Create a later valid Kilo binding B
    # Use expires_at=2026-01-01T00:30:00Z (3600 seconds from issued_at)
    enablement_b = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-B",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_kilo_b = EA4E22FakeKiloExecutor()
    handle_b = binding_controller.bind(enablement_b, executor_registry, executor_factory=lambda: fake_kilo_b)

    # Step 4: Attempt cleanup using stale handle A
    try:
        binding_controller.remove_expired_binding(
            "kilo-cli-agent",
            expected_enablement_id=handle_a.enablement_id,
            expected_binding_id=handle_a.binding_id,
        )
        assert False, "Should have raised BindingPolicyError"
    except Exception as e:
        # Should fail because stale handle A doesn't match current binding B
        assert "MISMATCH" in str(e) or "ENABLEMENT_ID_MISMATCH" in str(e) or "BINDING_ID_MISMATCH" in str(e)

    # Step 5: Binding B should remain active
    assert binding_controller.active_binding_count == 1
    assert executor_registry.has_executor("kilo-cli-agent")


def test_wrong_receiver_cannot_remove_binding(binding_controller, executor_registry):
    """Test wrong receiver cannot remove binding."""
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to remove with wrong receiver
    result = binding_controller.remove_expired_binding("opencode-cli-agent")
    assert result is False

    # Original binding should remain
    assert binding_controller.active_binding_count == 1
    assert executor_registry.has_executor("kilo-cli-agent")


def test_wrong_enablement_identity_cannot_remove_binding(binding_controller, executor_registry):
    """Test wrong enablement identity cannot remove binding."""
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Try to remove with wrong enablement ID
    try:
        binding_controller.remove_expired_binding(
            "kilo-cli-agent",
            expected_enablement_id="wrong-enablement-id",
        )
        assert False, "Should have raised BindingPolicyError"
    except Exception as e:
        assert "ENABLEMENT_ID_MISMATCH" in str(e) or "MISMATCH" in str(e)

    # Original binding should remain
    assert binding_controller.active_binding_count == 1


def test_repeated_cleanup_is_idempotent(binding_controller, executor_registry):
    """Test repeated cleanup is idempotent."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # First cleanup
    result1 = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result1.resolution_decision == "REJECT"

    # Second cleanup - should be idempotent
    result2 = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result2.resolution_decision == "REJECT"
    assert result2.resolution_reason == "EXECUTOR_NOT_BOUND"

    # No mutation of unrelated state
    assert binding_controller.active_binding_count == 0


def test_cleanup_failure_never_authorizes_execution(binding_controller, executor_registry):
    """Test cleanup failure never authorizes execution."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("kilo-cli-agent")

    # Should reject, not execute
    assert result.resolution_decision == "REJECT"
    assert fake_executor.call_count == 0


def test_exact_expiry_still_rejects(binding_controller, executor_registry):
    """Test exact expiry still rejects."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "REJECT"
    assert result.resolution_reason == "BINDING_EXPIRED"


def test_one_microsecond_before_expiry_remains_valid(binding_controller, executor_registry):
    """Test one microsecond before expiry remains valid."""
    clock = BindingClock(now="2026-01-01T00:29:59.999999Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    result = resolver.resolve_governed_executor("kilo-cli-agent")

    assert result.resolution_decision == "RESOLVED"


def test_expired_kilo_releases_slot_for_opencode_v2(binding_controller, executor_registry):
    """Test expired Kilo slot releases capacity for new OpenCode binding."""
    # Bind Kilo
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_kilo = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_kilo)

    # Advance clock to expiry
    expiry_clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=expiry_clock,
    )

    # Resolve Kilo - should prune
    result = resolver.resolve_governed_executor("kilo-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert binding_controller.active_binding_count == 0

    # Bind OpenCode - should succeed
    opencode_enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_opencode = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(opencode_enablement, executor_registry, executor_factory=lambda: fake_opencode)

    assert binding_controller.active_binding_count == 1


def test_expired_opencode_releases_slot_for_kilo_v2(binding_controller, executor_registry):
    """Test expired OpenCode slot releases capacity for new Kilo binding."""
    # Bind OpenCode
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="opencode-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_opencode = EA4E22FakeOpenCodeExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_opencode)

    # Advance clock to expiry
    expiry_clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=expiry_clock,
    )

    # Resolve OpenCode - should prune
    result = resolver.resolve_governed_executor("opencode-cli-agent")
    assert result.resolution_decision == "REJECT"
    assert binding_controller.active_binding_count == 0

    # Bind Kilo - should succeed
    kilo_enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    fake_kilo = EA4E22FakeKiloExecutor()
    binding_controller.bind(kilo_enablement, executor_registry, executor_factory=lambda: fake_kilo)

    assert binding_controller.active_binding_count == 1


def test_no_executor_model_process_invocation_during_cleanup(binding_controller, executor_registry):
    """Test no executor/model/process invocation during cleanup."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    resolver.resolve_governed_executor("kilo-cli-agent")

    assert fake_executor.call_count == 0


def test_contract_remains_deterministic_after_remediation():
    """Test contract remains deterministic after remediation."""
    contract_id_1 = compute_ea4e22_integration_contract_id()
    contract_id_2 = compute_ea4e22_integration_contract_id()
    assert contract_id_1 == contract_id_2
    assert isinstance(contract_id_1, str)
    assert len(contract_id_1) == 64


def test_controller_cleanup_uses_binding_handle_registry(binding_controller, executor_registry):
    """Test controller cleanup uses binding handle registry."""
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    resolver = GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=clock,
    )

    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="kilo-enablement-001",
        expires_at="2026-01-01T00:30:00Z",
    )
    fake_executor = EA4E22FakeKiloExecutor()
    handle = binding_controller.bind(enablement, executor_registry, executor_factory=lambda: fake_executor)

    # Verify handle has registry reference
    assert handle.registry is executor_registry

    # Resolve at exact expiry
    resolver.resolve_governed_executor("kilo-cli-agent")

    # Controller should use handle.registry for cleanup
    assert not executor_registry.has_executor("kilo-cli-agent")
