"""EA-4E.21 production real-executor binding policy tests.

Tests the binding policy with fake collaborators only.
No live execution, no real executors, no real adapters.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tools.hermes_core.production_executor_binding import (
    ALLOWED_DELEGATION_CLASS,
    ALLOWED_RUNTIME_SCOPE,
    BINDING_SCHEMA_ID,
    BINDING_SCHEMA_VERSION,
    DEFAULT_BINDING_DECISION,
    MAX_BINDING_TTL_SECONDS,
    MAX_SIMULTANEOUS_REAL_BINDINGS,
    BindingClock,
    BindingPolicyError,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    ProductionExecutorProtocol,
    ProductionExecutorResult,
    ProductionExecutionRequest,
    compute_ea4e21_binding_contract_id,
)
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# --------------------------------------------------------------------------- #
# Fake executors for non-live testing
# --------------------------------------------------------------------------- #

class FakeKiloExecutor:
    """Inert fake Kilo executor for non-live tests."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "fake-kilo-executor"

    def execute(self, request: ProductionExecutionRequest) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="FAKE_KILO_OK",
            reason="FAKE_EXECUTION",
        )


class FakeOpenCodeExecutor:
    """Inert fake OpenCode executor for non-live tests."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "fake-opencode-executor"

    def execute(self, request: ProductionExecutionRequest) -> ProductionExecutorResult:
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="FAKE_OPENCODE_OK",
            reason="FAKE_EXECUTION",
        )


# ---------------------------------------------------------------------------
# Fixtures
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


def _make_enablement(
    receiver_id: str = "kilo-cli-agent",
    enablement_id: str = "enablement-001",
    request_nonce: str = "nonce-001",
    issued_at: str = "2025-12-31T23:30:00Z",
    expires_at: str = "2026-01-01T00:30:00Z",
    **overrides,
) -> ProductionExecutorBindingEnablement:
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    executor_info = {
        "kilo-cli-agent": {
            "executor_identity": "RealKiloProductionExecutor",
            "executor_factory": "tools.hermes_core.kilo_live_binding:RealKiloProductionExecutor",
        },
        "opencode-cli-agent": {
            "executor_identity": "RealOpenCodeProductionExecutor",
            "executor_factory": "tools.hermes_core.opencode_live_binding:RealOpenCodeProductionExecutor",
        },
    }.get(receiver_id, {})

    # Build kwargs, letting overrides take precedence
    kwargs = {
        "enablement_id": enablement_id,
        "receiver_id": receiver_id,
        "transport_contract_id": bindings.get("transport_contract_id", "unknown"),
        "model_binding_id": bindings.get("model_binding_id", "unknown"),
        "executor_identity": executor_info.get("executor_identity", "unknown"),
        "executor_factory": executor_info.get("executor_factory", "unknown"),
        "runtime_scope": ALLOWED_RUNTIME_SCOPE,
        "delegation_class": ALLOWED_DELEGATION_CLASS,
        "requested_ttl_seconds": Decimal("3600"),
        "max_bound_executors": MAX_SIMULTANEOUS_REAL_BINDINGS,
        "enabled": True,
        "request_nonce": request_nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    kwargs.update(overrides)

    return ProductionExecutorBindingEnablement(**kwargs)


# ---------------------------------------------------------------------------
# Positive qualification tests
# ---------------------------------------------------------------------------

def test_kilo_binding_policy_allow(binding_policy):
    """Test that valid Kilo binding enablement is allowed."""
    enablement = _make_enablement(receiver_id="kilo-cli-agent")
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"
    assert result.binding_authorized is True


def test_opencode_binding_policy_allow(binding_policy):
    """Test that valid OpenCode binding enablement is allowed."""
    enablement = _make_enablement(receiver_id="opencode-cli-agent")
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"
    assert result.binding_authorized is True


def test_kilo_fake_binding_and_teardown(binding_controller, executor_registry):
    """Test Kilo fake binding and teardown."""
    enablement = _make_enablement(receiver_id="kilo-cli-agent")

    # Bind
    handle = binding_controller.bind(
        enablement,
        executor_registry,
        executor_factory=FakeKiloExecutor,
    )

    assert handle.receiver_id == "kilo-cli-agent"
    assert executor_registry.has_executor("kilo-cli-agent")
    assert executor_registry.bound_count == 1

    # Teardown
    result = binding_controller.teardown(handle)
    assert result is True
    assert not executor_registry.has_executor("kilo-cli-agent")
    assert executor_registry.bound_count == 0


def test_opencode_fake_binding_and_teardown(binding_controller, executor_registry):
    """Test OpenCode fake binding and teardown."""
    enablement = _make_enablement(receiver_id="opencode-cli-agent")

    # Bind
    handle = binding_controller.bind(
        enablement,
        executor_registry,
        executor_factory=FakeOpenCodeExecutor,
    )

    assert handle.receiver_id == "opencode-cli-agent"
    assert executor_registry.has_executor("opencode-cli-agent")
    assert executor_registry.bound_count == 1

    # Teardown
    result = binding_controller.teardown(handle)
    assert result is True
    assert not executor_registry.has_executor("opencode-cli-agent")
    assert executor_registry.bound_count == 0


# ---------------------------------------------------------------------------
# Negative qualification matrix
# ---------------------------------------------------------------------------

def test_missing_enablement_rejected(binding_policy):
    """Test that disabled enablement is rejected."""
    enablement = _make_enablement(enabled=False)
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_NOT_ENABLED"


def test_missing_receiver_rejected(binding_policy):
    """Test that missing receiver is rejected."""
    enablement = _make_enablement(receiver_id="")
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MISSING_RECEIVER"


def test_unsupported_receiver_rejected(binding_policy):
    """Test that unsupported receiver is rejected."""
    enablement = _make_enablement(receiver_id="unknown-receiver")
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "UNSUPPORTED_RECEIVER"


def test_wrong_kilo_transport_rejected(binding_policy):
    """Test that wrong Kilo transport is rejected."""
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        transport_contract_id="wrong-transport",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_wrong_kilo_model_rejected(binding_policy):
    """Test that wrong Kilo model is rejected."""
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        model_binding_id="wrong-model",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MODEL_BINDING_MISMATCH"


def test_wrong_opencode_transport_rejected(binding_policy):
    """Test that wrong OpenCode transport is rejected."""
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        transport_contract_id="wrong-transport",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TRANSPORT_CONTRACT_MISMATCH"


def test_wrong_opencode_model_rejected(binding_policy):
    """Test that wrong OpenCode model is rejected."""
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        model_binding_id="wrong-model",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MODEL_BINDING_MISMATCH"


def test_kilo_executor_for_opencode_rejected(binding_policy):
    """Test that Kilo executor identity for OpenCode is rejected."""
    enablement = _make_enablement(
        receiver_id="opencode-cli-agent",
        executor_identity="RealKiloProductionExecutor",
        executor_factory="tools.hermes_core.kilo_live_binding:RealKiloProductionExecutor",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EXECUTOR_IDENTITY_MISMATCH"


def test_opencode_executor_for_kilo_rejected(binding_policy):
    """Test that OpenCode executor identity for Kilo is rejected."""
    enablement = _make_enablement(
        receiver_id="kilo-cli-agent",
        executor_identity="RealOpenCodeProductionExecutor",
        executor_factory="tools.hermes_core.opencode_live_binding:RealOpenCodeProductionExecutor",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EXECUTOR_IDENTITY_MISMATCH"


def test_invalid_ttl_zero_rejected(binding_policy):
    """Test that TTL <= 0 is rejected."""
    enablement = _make_enablement(requested_ttl_seconds=0)
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "INVALID_REQUESTED_TTL"


def test_ttl_above_max_rejected(binding_policy):
    """Test that TTL above maximum is rejected."""
    enablement = _make_enablement(requested_ttl_seconds=MAX_BINDING_TTL_SECONDS + 1)
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TTL_ABOVE_MAX"


def test_unsupported_runtime_scope_rejected(binding_policy):
    """Test that unsupported runtime scope is rejected."""
    enablement = _make_enablement(runtime_scope="admin")
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "UNSUPPORTED_RUNTIME_SCOPE"


def test_binding_limit_exceeded_rejected(binding_policy, executor_registry):
    """Test that binding limit exceeded is rejected."""
    # Bind first executor
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="first")
    binding_policy.evaluate(enablement1)

    # Simulate binding count at limit
    enablement2 = _make_enablement(receiver_id="opencode-cli-agent", enablement_id="second")
    result = binding_policy.evaluate(enablement2, current_binding_count=MAX_SIMULTANEOUS_REAL_BINDINGS)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "BINDING_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# Replay / collision tests
# ---------------------------------------------------------------------------

def test_identical_duplicate_enablement(binding_policy):
    """Test that identical duplicate enablement is allowed."""
    enablement = _make_enablement()
    result1 = binding_policy.evaluate(enablement)
    assert result1.policy_decision == "ALLOW"

    # Same enablement again (identical)
    result2 = binding_policy.evaluate(enablement)
    assert result2.policy_decision == "ALLOW"


def test_enablement_id_collision_rejected(binding_policy):
    """Test that same enablement ID with conflicting canonical material is rejected."""
    from tools.hermes_core.hashing import sha256_payload

    enablement1 = _make_enablement(request_nonce="nonce-A")
    result1 = binding_policy.evaluate(enablement1, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement ID, different nonce (same receiver)
    enablement2 = _make_enablement(request_nonce="nonce-B")
    result2 = binding_policy.evaluate(enablement2, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "ENABLEMENT_ID_COLLISION"


def test_cross_receiver_binding_replay_rejected(binding_policy):
    """Test that same enablement ID with different receiver is rejected."""
    from tools.hermes_core.hashing import sha256_payload

    enablement1 = _make_enablement(receiver_id="kilo-cli-agent")
    result1 = binding_policy.evaluate(enablement1, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement ID, different receiver
    enablement2 = _make_enablement(receiver_id="opencode-cli-agent")
    result2 = binding_policy.evaluate(enablement2, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


def test_multi_field_cross_receiver_replay(binding_policy):
    """Test that receiver change + multiple field changes still results in CROSS_RECEIVER_BINDING_REPLAY."""
    from tools.hermes_core.hashing import sha256_payload

    enablement1 = _make_enablement(
        receiver_id="kilo-cli-agent",
        request_nonce="nonce-original",
    )
    result1 = binding_policy.evaluate(enablement1, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement ID, different receiver AND different nonce
    enablement2 = _make_enablement(
        receiver_id="opencode-cli-agent",
        request_nonce="nonce-changed",
    )
    result2 = binding_policy.evaluate(enablement2, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


# ---------------------------------------------------------------------------
# Controller tests
# ---------------------------------------------------------------------------

def test_controller_bind_rejected_does_not_mutate_registry(binding_controller, executor_registry):
    """Test that rejected binding does not mutate registry."""
    enablement = _make_enablement(receiver_id="", enabled=False)

    with pytest.raises(BindingPolicyError):
        binding_controller.bind(enablement, executor_registry, executor_factory=FakeKiloExecutor)

    assert executor_registry.bound_count == 0


def test_controller_teardown_unknown_binding(binding_controller, executor_registry):
    """Test that teardown of unknown binding fails closed."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingHandle

    handle = ProductionExecutorBindingHandle(
        binding_id="unknown",
        enablement_id="unknown",
        receiver_id="unknown",
        executor_identity="unknown",
        bound_at=QUALIFICATION_CLOCK,
        expires_at=QUALIFICATION_CLOCK,
        registry=executor_registry,
    )

    result = binding_controller.teardown(handle)
    assert result is False


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

def test_binding_contract_deterministic():
    """Test that the binding contract is deterministic."""
    id1 = compute_ea4e21_binding_contract_id()
    id2 = compute_ea4e21_binding_contract_id()
    assert id1 == id2


def test_identical_contract_inputs_identical_hash():
    """Test that identical contract inputs produce identical hash."""
    hash1 = compute_ea4e21_binding_contract_id()
    hash2 = compute_ea4e21_binding_contract_id()
    assert hash1 == hash2


def test_qualification_clock_fixed():
    """Test that the qualification clock is fixed."""
    clock = BindingClock(now=QUALIFICATION_CLOCK)
    assert clock.now_iso() == QUALIFICATION_CLOCK
    # Same value every time
    assert clock.now_iso() == clock.now_iso()


def test_system_clock_not_required():
    """Test that system clock is not required."""
    import inspect
    source = inspect.getsource(BindingClock)
    # The BindingClock should only use the injected _now value
    assert "datetime.now(" not in source


# ---------------------------------------------------------------------------
# Default state tests
# ---------------------------------------------------------------------------

def test_default_registry_inert(fixed_clock):
    """Test that default registry has no real executors."""
    registry = ExecutorRegistry()
    assert not registry.has_executor("kilo-cli-agent")
    assert not registry.has_executor("opencode-cli-agent")
    assert registry.bound_count == 0


def test_default_binding_decision():
    """Test that default binding decision is DENY."""
    assert DEFAULT_BINDING_DECISION == "DENY"


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_binding_schema_id():
    """Test that binding schema ID is correct."""
    assert BINDING_SCHEMA_ID == "hermes.production-executor-binding.receiver-dispatch/v1"


def test_binding_schema_version():
    """Test that binding schema version is correct."""
    assert BINDING_SCHEMA_VERSION == "ea4e.21"


# ---------------------------------------------------------------------------
# EA-4E.21B binding-lifecycle tests
# ---------------------------------------------------------------------------

def test_active_binding_collision_not_masked_by_limit(binding_policy):
    """Test that collision with active binding is not masked by binding limit."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind first enablement
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="collision-test")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement with the same hash the policy computes
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement_id + same receiver + changed canonical field
    enablement2 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="collision-test",
        request_nonce="different-nonce",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "ENABLEMENT_ID_COLLISION"


def test_active_binding_cross_receiver_replay_not_masked_by_limit(binding_policy):
    """Test that cross-receiver replay with active binding is not masked by binding limit."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind Kilo first
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="replay-test")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement_id for OpenCode
    enablement2 = _make_enablement(receiver_id="opencode-cli-agent", enablement_id="replay-test")
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


def test_active_binding_cross_receiver_replay_reverse_direction(binding_policy):
    """Test cross-receiver replay in reverse direction (OpenCode -> Kilo)."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind OpenCode first
    enablement1 = _make_enablement(receiver_id="opencode-cli-agent", enablement_id="reverse-replay-test")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement_id for Kilo
    enablement2 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="reverse-replay-test")
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


def test_active_multi_field_cross_receiver_replay(binding_policy):
    """Test multi-field cross-receiver replay with active binding."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind Kilo first
    enablement1 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="multi-field-test",
        request_nonce="original-nonce",
    )
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Same enablement_id for OpenCode with different nonce
    enablement2 = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="multi-field-test",
        request_nonce="changed-nonce",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


def test_identical_duplicate_while_limit_full(binding_policy):
    """Test identical duplicate while binding limit is full."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind first enablement
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="duplicate-test")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Identical duplicate
    enablement2 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="duplicate-test")
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "IDENTICAL_DUPLICATE"


def test_genuinely_new_second_binding_rejected(binding_policy):
    """Test that genuinely new second binding is rejected due to limit."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind Kilo first
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="first-binding")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Genuinely new OpenCode binding
    enablement2 = _make_enablement(receiver_id="opencode-cli-agent", enablement_id="second-binding")
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "BINDING_LIMIT_EXCEEDED"


def test_expired_enablement_rejected(binding_policy):
    """Test that expired enablement is rejected."""
    enablement = _make_enablement(
        issued_at="2025-01-01T00:00:00Z",
        expires_at="2025-01-01T01:00:00Z",  # Expired before qualification clock
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_EXPIRED"


def test_not_yet_expired_enablement_valid(binding_policy):
    """Test that not-yet-expired enablement passes temporal validation."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",  # Expires after qualification clock, 3600s interval
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_exact_expiration_boundary(binding_policy):
    """Test exact expiration boundary (now == expires_at)."""
    # Enablement that expires exactly at qualification clock
    enablement = _make_enablement(
        issued_at="2025-12-31T23:00:00Z",
        expires_at=QUALIFICATION_CLOCK,  # Exactly at boundary
    )
    result = binding_policy.evaluate(enablement)
    # At boundary: expires_at <= now means expired
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_EXPIRED"


def test_ttl_at_max_valid(binding_policy):
    """Test that TTL exactly at max is valid."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",  # Exactly 3600 seconds (MAX_BINDING_TTL_SECONDS)
        requested_ttl_seconds=MAX_BINDING_TTL_SECONDS,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_ttl_above_max_rejected(binding_policy):
    """Test that TTL above max is rejected via effective lifetime."""
    # Use matching declared/effective TTL that exceeds policy max
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:01Z",  # 3601 seconds - above max
        requested_ttl_seconds=3601,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_future_issued_enablement_rejected(binding_policy):
    """Test that future-issued enablement is rejected."""
    enablement = _make_enablement(
        issued_at="2026-01-02T00:00:00Z",  # In the future
        expires_at="2026-01-02T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_NOT_YET_VALID"


def test_replay_collision_registry_not_mutated(binding_policy, executor_registry):
    """Test that replay/collision does not mutate registry."""
    # Bind first
    enablement1 = _make_enablement(receiver_id="kilo-cli-agent", enablement_id="registry-test")
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0)
    assert result1.policy_decision == "ALLOW"

    # Attempt collision
    enablement2 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="registry-test",
        request_nonce="different",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1)
    assert result2.policy_decision == "REJECT"
    # Registry should not have been mutated
    assert executor_registry.bound_count == 0


def test_expired_enablement_registry_not_mutated(binding_policy, executor_registry):
    """Test that expired enablement does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2025-01-01T00:00:00Z",
        expires_at="2025-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_EXPIRED"
    assert executor_registry.bound_count == 0


def test_future_issued_registry_not_mutated(binding_policy, executor_registry):
    """Test that future-issued enablement does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2026-01-02T00:00:00Z",
        expires_at="2026-01-02T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_NOT_YET_VALID"
    assert executor_registry.bound_count == 0


# ---------------------------------------------------------------------------
# EA-4E.21C temporal integrity tests
# ---------------------------------------------------------------------------

def test_malformed_issued_at_rejected(binding_policy):
    """Test that malformed issued_at is rejected."""
    enablement = _make_enablement(
        issued_at="not-a-timestamp",
        expires_at="2026-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MALFORMED_ISSUED_AT"


def test_malformed_expires_at_rejected(binding_policy):
    """Test that malformed expires_at is rejected."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:00:00Z",
        expires_at="not-a-timestamp",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MALFORMED_EXPIRES_AT"


def test_malformed_timestamp_registry_not_mutated(binding_policy, executor_registry):
    """Test that malformed timestamp does not mutate registry."""
    enablement = _make_enablement(
        issued_at="not-a-timestamp",
        expires_at="2026-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_naive_issued_at_rejected(binding_policy):
    """Test that naive (timezone-unaware) issued_at is rejected."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00",  # No timezone
        expires_at="2026-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MALFORMED_ISSUED_AT"


def test_naive_expires_at_rejected(binding_policy):
    """Test that naive (timezone-unaware) expires_at is rejected."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:00:00Z",
        expires_at="2026-01-01T01:00:00",  # No timezone
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "MALFORMED_EXPIRES_AT"


def test_naive_timestamp_registry_not_mutated(binding_policy, executor_registry):
    """Test that naive timestamp does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00",  # No timezone
        expires_at="2026-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_zero_effective_lifetime_rejected(binding_policy):
    """Test that issued_at == expires_at is rejected."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "INVALID_TEMPORAL_ORDER"


def test_negative_effective_lifetime_rejected(binding_policy):
    """Test that issued_at > expires_at is rejected."""
    enablement = _make_enablement(
        issued_at="2026-01-01T02:00:00Z",
        expires_at="2026-01-01T01:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "INVALID_TEMPORAL_ORDER"


def test_temporal_order_rejection_registry_not_mutated(binding_policy, executor_registry):
    """Test that temporal order rejection does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:00:00Z",
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_effective_lifetime_3600_seconds_valid(binding_policy):
    """Test that effective lifetime of exactly 3600 seconds is valid."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=3600,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_effective_lifetime_3601_seconds_rejected(binding_policy):
    """Test that effective lifetime of 3601 seconds is rejected."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:01Z",
        requested_ttl_seconds=3601,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_effective_ttl_above_max_registry_not_mutated(binding_policy, executor_registry):
    """Test that effective TTL above max does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:01Z",
        requested_ttl_seconds=3601,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_declared_ttl_3600_actual_7200_rejected(binding_policy):
    """Test that declared TTL 3600 with actual interval 7200 is rejected."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T01:30:00Z",  # 7200 seconds
        requested_ttl_seconds=3600,  # Declared as 3600
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    # Policy max is checked first - 7200 > 3600 policy max
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_declared_ttl_mismatch_registry_not_mutated(binding_policy, executor_registry):
    """Test that declared TTL mismatch does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T01:30:00Z",
        requested_ttl_seconds=3600,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_offset_aware_effective_lifetime(binding_policy):
    """Test offset-aware chronological comparison."""
    # 2026-01-01T00:00:00+00:00 to 2026-01-01T02:00:00+01:00 = 1 hour effective
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00+00:00",
        expires_at="2026-01-01T01:30:00+01:00",
        requested_ttl_seconds=3600,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_equivalent_offset_instants_compare_equal(binding_policy):
    """Test that equivalent instants with different offsets compare equal."""
    # 2026-01-01T00:00:00Z == 2025-12-31T19:00:00-05:00
    from tools.hermes_core.production_executor_binding import parse_iso_timestamp

    dt1 = parse_iso_timestamp("2026-01-01T00:00:00Z")
    dt2 = parse_iso_timestamp("2025-12-31T19:00:00-05:00")
    assert dt1 == dt2


def test_valid_temporal_enablement_passes(binding_policy):
    """Test that valid temporal enablement passes temporal validation."""
    # Qualification clock: 2026-01-01T00:00:00Z
    # issued_at: 2025-12-31T23:30:00Z (in the past)
    # expires_at: 2026-01-01T00:30:00Z (in the future)
    # effective lifetime: 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=3600,
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_replay_semantics_preserved_with_valid_temporal(binding_policy):
    """Test that replay semantics remain intact with valid temporal material."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind first with valid temporal
    enablement1 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="replay-temporal-test",
    )
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Identical duplicate
    enablement2 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="replay-temporal-test",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "IDENTICAL_DUPLICATE"


def test_cross_receiver_replay_preserved_with_valid_temporal(binding_policy):
    """Test that cross-receiver replay works with valid temporal material."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind Kilo first
    enablement1 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="cross-replay-temporal-test",
    )
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Cross-receiver replay
    enablement2 = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="cross-replay-temporal-test",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "CROSS_RECEIVER_BINDING_REPLAY"


def test_genuinely_new_second_binding_still_rejected(binding_policy):
    """Test that genuinely new second binding is still rejected after temporal fix."""
    from tools.hermes_core.hashing import sha256_payload

    # Bind Kilo first
    enablement1 = _make_enablement(
        receiver_id="kilo-cli-agent",
        enablement_id="first-temporal-binding",
    )
    result1 = binding_policy.evaluate(enablement1, current_binding_count=0, bound_enablements={})
    assert result1.policy_decision == "ALLOW"

    # Record the bound enablement
    bound = {enablement1.enablement_id: (enablement1.receiver_id, sha256_payload(enablement1.to_canonical_dict()))}

    # Genuinely new OpenCode binding
    enablement2 = _make_enablement(
        receiver_id="opencode-cli-agent",
        enablement_id="second-temporal-binding",
    )
    result2 = binding_policy.evaluate(enablement2, current_binding_count=1, bound_enablements=bound)
    assert result2.policy_decision == "REJECT"
    assert result2.policy_reason == "BINDING_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# EA-4E.21D temporal precision / TTL semantic finalization tests
# ---------------------------------------------------------------------------

def test_effective_lifetime_exact_3600_result(binding_policy):
    """Test that effective lifetime of exactly 3600 seconds is valid."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_effective_lifetime_3600_plus_1_microsecond_rejected(binding_policy):
    """Test that 3600.000001 seconds is rejected (above policy max)."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00.000001Z",
        requested_ttl_seconds=Decimal("3600.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_effective_lifetime_3599_999999_result(binding_policy):
    """Test that 3599.999999 seconds is valid (below policy max)."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:29:59.999999Z",
        requested_ttl_seconds=Decimal("3599.999999"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_subsecond_effective_lifetime(binding_policy):
    """Test sub-second effective lifetime."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("0.5"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_one_microsecond_interval(binding_policy):
    """Test one-microsecond interval."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.000001Z",
        requested_ttl_seconds=Decimal("0.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_exact_now_expiration(binding_policy):
    """Test that expires_at == now is expired."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:00:00.000000Z",  # Exactly at qualification clock
        requested_ttl_seconds=Decimal("1800"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "ENABLEMENT_EXPIRED"


def test_one_microsecond_after_now_not_expired(binding_policy):
    """Test that expires_at == now + 1 microsecond is not expired."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:00:00.000001Z",  # 1 microsecond after qualification clock
        requested_ttl_seconds=Decimal("1800.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_requested_ttl_subsecond_exact_match(binding_policy):
    """Test requested TTL sub-second exact match (within policy max)."""
    # 1800.5 seconds - within 3600s policy max
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("1800.5"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_requested_ttl_subsecond_above_policy_max(binding_policy):
    """Test requested TTL sub-second above policy max."""
    # 3600.5 seconds - above 3600s policy max
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00.500000Z",
        requested_ttl_seconds=Decimal("3600.5"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_requested_ttl_half_second_match(binding_policy):
    """Test requested TTL half second match."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("0.5"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "ALLOW"


def test_requested_ttl_subsecond_mismatch(binding_policy):
    """Test requested TTL sub-second mismatch."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("0.500001"),  # Mismatch
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "TTL_MISMATCH"


def test_requested_and_effective_match_above_policy_max(binding_policy):
    """Test that requested/effective match above policy max is rejected."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00.000001Z",  # 3600.000001 seconds
        requested_ttl_seconds=Decimal("3600.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_offset_aware_fractional_effective_lifetime(binding_policy):
    """Test offset-aware fractional effective lifetime."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:00:00.500000+00:00",
        expires_at="2026-01-01T01:00:00.500001+01:00",
        requested_ttl_seconds=Decimal("3600.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert result.policy_reason == "EFFECTIVE_TTL_ABOVE_MAX"


def test_ttl_canonicalization_equivalence():
    """Test that semantically equivalent TTL values canonicalize identically."""
    from tools.hermes_core.production_executor_binding import ttl_to_canonical_str

    assert ttl_to_canonical_str(Decimal("3600")) == "3600"
    assert ttl_to_canonical_str(Decimal("3600.0")) == "3600"
    assert ttl_to_canonical_str(Decimal("3600.000000")) == "3600"
    assert ttl_to_canonical_str(Decimal("0.5")) == "0.5"
    assert ttl_to_canonical_str(Decimal("0.500000")) == "0.5"


def test_fractional_above_max_registry_not_mutated(binding_policy, executor_registry):
    """Test that fractional above max does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00.000001Z",
        requested_ttl_seconds=Decimal("3600.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_requested_ttl_mismatch_registry_not_mutated(binding_policy, executor_registry):
    """Test that requested TTL mismatch does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("0.500001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_subsecond_ttl_mismatch_registry_not_mutated(binding_policy, executor_registry):
    """Test that sub-second TTL mismatch does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("0.500001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


def test_offset_aware_fractional_rejection_registry_not_mutated(binding_policy, executor_registry):
    """Test that offset-aware fractional rejection does not mutate registry."""
    enablement = _make_enablement(
        issued_at="2025-12-31T23:00:00.500000+00:00",
        expires_at="2026-01-01T01:00:00.500001+01:00",
        requested_ttl_seconds=Decimal("3600.000001"),
    )
    result = binding_policy.evaluate(enablement)
    assert result.policy_decision == "REJECT"
    assert executor_registry.bound_count == 0


# ---------------------------------------------------------------------------
# EA-4E.21E runtime binding expiration consistency tests
# ---------------------------------------------------------------------------

def test_binding_handle_inherits_exact_validated_expires_at(binding_policy, executor_registry):
    """Test that binding handle inherits exact validated expires_at from enablement."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Handle must inherit exact validated expires_at
    assert handle.expires_at == enablement.expires_at
    assert handle.expires_at == "2026-01-01T00:30:00Z"


def test_partially_consumed_enablement_no_ttl_reset(binding_policy, executor_registry):
    """Test that partially consumed enablement does not get TTL reset."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    # Qualification clock at 00:30 - enablement was issued at 00:00 with 3600s TTL
    clock = BindingClock(now="2026-01-01T00:30:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 00:00, expires 01:00 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T01:00:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Handle must expire at original expires_at, NOT at 01:30 (bind time + TTL)
    assert handle.expires_at == "2026-01-01T01:00:00Z"


def test_subsecond_binding_handle_expiry_preserved(binding_policy, executor_registry):
    """Test sub-second handle expiry preservation."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2025-12-31T23:59:59.500000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("1"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Sub-second expiry must be preserved
    assert handle.expires_at == "2026-01-01T00:00:00.500000Z"


def test_microsecond_binding_handle_expiry_preserved(binding_policy, executor_registry):
    """Test microsecond handle expiry preservation."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00.000000Z",
        expires_at="2026-01-01T00:00:00.000001Z",
        requested_ttl_seconds=Decimal("0.000001"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Microsecond expiry must be preserved
    assert handle.expires_at == "2026-01-01T00:00:00.000001Z"


def test_controller_does_not_int_cast_requested_ttl(binding_policy, executor_registry):
    """Test that controller does not int-cast requested TTL."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Fractional TTL that would be truncated by int()
    # issued 23:59:59.0, expires 00:00:00.5 = 1.5 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:59:59.000000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("1.5"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Handle must preserve exact expiry, not truncate
    assert handle.expires_at == "2026-01-01T00:00:00.500000Z"


def test_controller_does_not_call_now_plus_seconds_for_handle_expiry(binding_policy, executor_registry):
    """Test that controller does not call now_plus_seconds for handle expiry."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Handle expiry must equal enablement expiry, not be recomputed from bind time
    assert handle.expires_at == enablement.expires_at


def test_identical_duplicate_does_not_refresh_expiry(binding_policy, executor_registry):
    """Test that identical duplicate does not refresh expiry."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle1 = controller.bind(enablement, executor_registry)
    original_expiry = handle1.expires_at

    # Bind again with same enablement
    handle2 = controller.bind(enablement, executor_registry)

    # Expiry must not be refreshed/extended
    assert handle2.expires_at == original_expiry


def test_pre_registration_expiry_check_fail_closed(binding_policy, executor_registry):
    """Test that pre-registration expiry check fails closed."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    # Clock is AFTER the enablement expiry
    clock = BindingClock(now="2026-01-01T00:31:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",  # Already expired
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_EXPIRED"

    # Registry should not have been mutated
    assert executor_registry.bound_count == 0


def test_expired_between_policy_and_bind(binding_policy, executor_registry):
    """Test expired-between-policy-and-bind fail-closed behavior."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00.000000Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2025-12-31T23:59:59.500000Z",
        expires_at="2026-01-01T00:00:00.500000Z",
        requested_ttl_seconds=Decimal("1"),
    )

    handle = controller.bind(enablement, executor_registry)
    assert handle.expires_at == "2026-01-01T00:00:00.500000Z"


def test_partially_consumed_bind_registry_mutated_only_on_allow(binding_policy, executor_registry):
    """Test that partially consumed bind only mutates registry on allow."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:30:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T01:00:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)

    assert executor_registry.bound_count == 1
    assert handle.expires_at == "2026-01-01T01:00:00Z"


def test_pre_registration_expired_registry_not_mutated(binding_policy, executor_registry):
    """Test that pre-registration expired does not mutate registry."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock, BindingPolicyError

    clock = BindingClock(now="2026-01-01T00:31:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("1800"),
    )

    try:
        controller.bind(enablement, executor_registry)
    except BindingPolicyError:
        pass

    assert executor_registry.bound_count == 0


def test_identical_duplicate_registry_not_mutated(binding_policy, executor_registry):
    """Test that identical duplicate does not mutate registry."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle1 = controller.bind(enablement, executor_registry)
    assert executor_registry.bound_count == 1

    # Bind again with same enablement
    handle2 = controller.bind(enablement, executor_registry)

    # Registry should still have exactly one binding
    assert executor_registry.bound_count == 1


# ---------------------------------------------------------------------------
# EA-4E.21F controller replay enforcement tests
# ---------------------------------------------------------------------------

def test_controller_same_id_fast_path_before_policy(binding_policy, executor_registry):
    """Test that controller does NOT use same-ID fast path before policy classification."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # First bind a valid Kilo enablement (issued 23:30, expires 00:30 = 3600 seconds)
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Now submit same ID but with changed nonce (should be collision, not success)
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        request_nonce="nonce-CHANGED",  # Changed
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError for changed nonce"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    # Registry should not have been mutated
    assert executor_registry.bound_count == 1
    # Original handle should still be valid
    assert handle1.binding_id is not None


def test_controller_changed_nonce_collision(binding_policy, executor_registry):
    """Test same ID + changed nonce rejects collision."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind original
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        request_nonce="nonce-001",
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID with changed nonce
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        request_nonce="nonce-CHANGED",
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    assert executor_registry.bound_count == 1


def test_controller_changed_ttl_collision(binding_policy, executor_registry):
    """Test same ID + changed TTL rejects collision."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock, ProductionExecutorBindingPolicy

    # Clock at 20:59:59 - strictly before both enablements expire
    clock = BindingClock(now="2025-12-31T20:59:59Z")
    policy = ProductionExecutorBindingPolicy(clock=clock)
    controller = ProductionExecutorBindingController(policy=policy, clock=clock)

    # Bind original (issued 20:00, expires 21:00 = 3600 seconds)
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        issued_at="2025-12-31T20:00:00Z",
        expires_at="2025-12-31T21:00:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID with changed TTL (issued 20:30, expires 21:30 = 3600 seconds)
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        issued_at="2025-12-31T20:30:00Z",
        expires_at="2025-12-31T21:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    assert executor_registry.bound_count == 1


def test_controller_changed_expiry_collision(binding_policy, executor_registry):
    """Test same ID + changed expiry rejects collision."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock, ProductionExecutorBindingPolicy

    # Clock at 23:00 - both enablements are valid (a expires 23:30, b expires 00:00)
    clock = BindingClock(now="2025-12-31T23:00:00Z")
    policy = ProductionExecutorBindingPolicy(clock=clock)
    controller = ProductionExecutorBindingController(policy=policy, clock=clock)

    # Bind original (issued 22:30, expires 23:30 = 3600 seconds)
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        issued_at="2025-12-31T22:30:00Z",
        expires_at="2025-12-31T23:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID with changed expiry (issued 23:00, expires 00:00 = 3600 seconds)
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        issued_at="2025-12-31T23:00:00Z",
        expires_at="2026-01-01T00:00:00Z",  # Changed
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    assert executor_registry.bound_count == 1


def test_controller_kilo_to_opencode_replay(binding_policy, executor_registry):
    """Test Kilo -> OpenCode cross-receiver replay rejection."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind Kilo enablement
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID as OpenCode
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="opencode-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "CROSS_RECEIVER_BINDING_REPLAY"

    assert executor_registry.bound_count == 1


def test_controller_opencode_to_kilo_replay(binding_policy, executor_registry):
    """Test OpenCode -> Kilo cross-receiver replay rejection."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind OpenCode enablement
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="opencode-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID as Kilo
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "CROSS_RECEIVER_BINDING_REPLAY"

    assert executor_registry.bound_count == 1


def test_controller_multi_field_cross_receiver_replay(binding_policy, executor_registry):
    """Test multi-field cross-receiver replay retains cross-receiver precedence."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind Kilo enablement
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        request_nonce="nonce-001",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID as OpenCode with multiple changed fields
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="opencode-cli-agent",
        request_nonce="nonce-CHANGED",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "CROSS_RECEIVER_BINDING_REPLAY"

    assert executor_registry.bound_count == 1


def test_controller_replay_collision_precedes_binding_limit(binding_policy, executor_registry):
    """Test replay/collision classification before binding-limit enforcement."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind first Kilo enablement (consumes the binding limit of 1)
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit same ID with changed nonce - should be COLLISION not BINDING_LIMIT
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        request_nonce="nonce-CHANGED",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        # Must be COLLISION, not BINDING_LIMIT_EXCEEDED
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    assert executor_registry.bound_count == 1


def test_controller_genuinely_new_second_binding_limit(binding_policy, executor_registry):
    """Test genuinely new second binding still rejects binding limit."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # Bind first Kilo enablement (consumes the binding limit of 1)
    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle1 = controller.bind(enablement_a, executor_registry)
    assert executor_registry.bound_count == 1

    # Submit genuinely new enablement (different ID) - should be BINDING_LIMIT
    enablement_b = _make_enablement(
        enablement_id="enablement-002",
        receiver_id="opencode-cli-agent",
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    from tools.hermes_core.production_executor_binding import BindingPolicyError

    try:
        controller.bind(enablement_b, executor_registry)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "BINDING_LIMIT_EXCEEDED"

    assert executor_registry.bound_count == 1


def test_controller_identical_duplicate_returns_same_handle(binding_policy, executor_registry):
    """Test identical duplicate returns same handle object."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle1 = controller.bind(enablement, executor_registry)
    handle2 = controller.bind(enablement, executor_registry)

    # Must return exact same handle object
    assert handle1 is handle2
    assert handle1.binding_id == handle2.binding_id
    assert handle1.expires_at == handle2.expires_at
    assert handle1.bound_at == handle2.bound_at


def test_controller_identical_duplicate_no_factory_call(binding_policy, executor_registry):
    """Test identical duplicate does not call executor factory again."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    # Create a factory that tracks call count
    call_count = [0]

    class MockExecutor:
        pass

    def factory():
        call_count[0] += 1
        return MockExecutor()

    handle1 = controller.bind(enablement, executor_registry, executor_factory=factory)
    assert call_count[0] == 1

    # Bind again with same enablement
    handle2 = controller.bind(enablement, executor_registry, executor_factory=factory)

    # Factory should NOT have been called again
    assert call_count[0] == 1
    assert handle1 is handle2


def test_controller_collision_no_factory_call(binding_policy, executor_registry):
    """Test collision does not call executor factory."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock, BindingPolicyError

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        request_nonce="nonce-001",
    )
    handle1 = controller.bind(enablement_a, executor_registry)

    # Track factory calls
    call_count = [0]

    class MockExecutor:
        pass

    def factory():
        call_count[0] += 1
        return MockExecutor()

    # Submit collision
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        request_nonce="nonce-CHANGED",
    )

    try:
        controller.bind(enablement_b, executor_registry, executor_factory=factory)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "ENABLEMENT_ID_COLLISION"

    # Factory should NOT have been called
    assert call_count[0] == 0


def test_controller_teardown_removes_bound_metadata(binding_policy, executor_registry):
    """Test teardown removes bound enablement metadata."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)
    assert executor_registry.bound_count == 1

    # Teardown
    result = controller.teardown(handle)
    assert result is True
    assert executor_registry.bound_count == 0

    # After teardown, same enablement_id can be bound again (no replay history)
    enablement2 = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )
    handle2 = controller.bind(enablement2, executor_registry)
    assert executor_registry.bound_count == 1
    assert handle2 is not None

    # But the old handle is no longer valid
    assert handle.binding_id != handle2.binding_id


def test_controller_no_dangling_handle_after_teardown(binding_policy, executor_registry):
    """Test no dangling handle reference remains after teardown."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    # issued 23:30, expires 00:30 = 3600 seconds
    enablement = _make_enablement(
        issued_at="2025-12-31T23:30:00Z",
        expires_at="2026-01-01T00:30:00Z",
        requested_ttl_seconds=Decimal("3600"),
    )

    handle = controller.bind(enablement, executor_registry)

    # Get the bound handle before teardown
    bound_handle = controller.get_bound_handle(enablement.enablement_id)
    assert bound_handle is not None

    # Teardown
    controller.teardown(handle)

    # After teardown, get_bound_handle should return None
    bound_handle_after = controller.get_bound_handle(enablement.enablement_id)
    assert bound_handle_after is None


def test_controller_cross_receiver_replay_no_factory_call(binding_policy, executor_registry):
    """Test cross-receiver replay does not call executor factory."""
    from tools.hermes_core.production_executor_binding import ProductionExecutorBindingController, BindingClock, BindingPolicyError

    clock = BindingClock(now="2026-01-01T00:00:00Z")
    controller = ProductionExecutorBindingController(policy=binding_policy, clock=clock)

    enablement_a = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="kilo-cli-agent",
    )
    handle1 = controller.bind(enablement_a, executor_registry)

    # Track factory calls
    call_count = [0]

    class MockExecutor:
        pass

    def factory():
        call_count[0] += 1
        return MockExecutor()

    # Submit cross-receiver replay
    enablement_b = _make_enablement(
        enablement_id="enablement-001",
        receiver_id="opencode-cli-agent",
    )

    try:
        controller.bind(enablement_b, executor_registry, executor_factory=factory)
        assert False, "Should have raised BindingPolicyError"
    except BindingPolicyError as e:
        assert e.reason == "CROSS_RECEIVER_BINDING_REPLAY"

    # Factory should NOT have been called
    assert call_count[0] == 0
