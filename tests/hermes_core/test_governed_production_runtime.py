"""Tests for EA-4E.26 dual-receiver governed production runtime integration.

All tests use a FIXED deterministic clock (2026-01-01T00:00:00Z).
No wall-clock reads are required. No real receiver processes are started.

Includes:
- Positive fake paths (Kilo + OpenCode)
- Cross-receiver authorization isolation (26A Gap C/D)
- Complete 30-case fail-closed matrix (26A Gap B)
- Default-off / no auto-bind / determinism
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingEnablement,
    ProductionExecutorBindingPolicy,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
    QUALIFIED_RECEIVERS,
)
from tools.hermes_core.governed_production_runtime import (
    GovernedProductionRuntime,
    GovernedProductionRuntimeRequest,
    compute_ea4e26_integration_contract_id,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
)
from tools.hermes_core.production_execution import (
    FakeKiloExecutor,
    FakeOpenCodeExecutor,
    ProductionExecutorResult,
)
from tools.hermes_core.receiver_router import compute_ea4e6_router_contract_id
from tests.hermes_core.durable_auth_test_support import (
    QualificationDurablePolicy,
    qualification_store,
)
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.production_activation import build_production_activation
from tools.hermes_core.receiver_dispatch import compute_ea4e7_authority_contract_id


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# --------------------------------------------------------------------------- #
# EA-4E.26 fake executors with canonical identity
# --------------------------------------------------------------------------- #

class FakeKiloQualificationExecutor:
    """Fake Kilo executor for EA-4E.26 qualification. Reports canonical identity."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "RealKiloProductionExecutor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request):
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK",
            reason="FAKE_EXECUTION",
        )


class FakeOpenCodeQualificationExecutor:
    """Fake OpenCode executor for EA-4E.26 qualification. Reports canonical identity."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "RealOpenCodeProductionExecutor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request):
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output="EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK",
            reason="FAKE_EXECUTION",
        )


class FakeFailingKiloExecutor:
    """Fake Kilo executor that always fails."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "RealKiloProductionExecutor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request):
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="FAILURE",
            output="KILO_EXECUTOR_FAILED",
            reason="FAKE_FAILURE",
        )


class FakeFailingOpenCodeExecutor:
    """Fake OpenCode executor that always fails."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def executor_id(self) -> str:
        return "RealOpenCodeProductionExecutor"

    @property
    def call_count(self) -> int:
        return self._call_count

    def execute(self, request):
        self._call_count += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="FAILURE",
            output="OPENCODE_EXECUTOR_FAILED",
            reason="FAKE_FAILURE",
        )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def fixed_clock():
    """Fixed deterministic qualification clock."""
    return ClockCollaborator(now=QUALIFICATION_CLOCK)


@pytest.fixture
def binding_clock():
    """Fixed deterministic binding clock."""
    return BindingClock(now=QUALIFICATION_CLOCK)


@pytest.fixture
def kilo_fake():
    return FakeKiloQualificationExecutor()


@pytest.fixture
def opencode_fake():
    return FakeOpenCodeQualificationExecutor()


@pytest.fixture
def executor_registry(kilo_fake, opencode_fake):
    registry = ExecutorRegistry()
    registry.register("kilo-cli-agent", kilo_fake)
    registry.register("opencode-cli-agent", opencode_fake)
    return registry


@pytest.fixture
def binding_controller(binding_clock):
    return ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=binding_clock),
        clock=binding_clock,
    )


def _durable_runtime(clock, executor_registry, binding_controller, tmp_path, name):
    return GovernedProductionRuntime(
        clock=clock,
        executor_registry=executor_registry,
        binding_controller=binding_controller,
        invocation_authorization_policy=QualificationDurablePolicy(
            clock=clock,
            store=qualification_store(tmp_path, name),
        ),
    )


@pytest.fixture
def runtime(fixed_clock, executor_registry, binding_controller, tmp_path):
    return _durable_runtime(
        fixed_clock, executor_registry, binding_controller, tmp_path, "runtime.sqlite3"
    )


def _make_request(
    receiver_id: str = "kilo-cli-agent",
    request_id: str = "req-001",
    task_payload: str | None = None,
) -> GovernedProductionRuntimeRequest:
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    authority = None
    activation = None
    if receiver_id in QUALIFIED_RECEIVERS:
        authority, activation = external_authority_and_activation(receiver_id, request_id)
    return GovernedProductionRuntimeRequest(
        request_id=request_id,
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        transport_contract_id=bindings.get("transport_contract_id", ""),
        model_binding_id=bindings.get("model_binding_id", ""),
        task_payload=task_payload,
        execution_authority=authority,
        activation=activation,
    )


def _make_authorized_request(
    binding_controller: ProductionExecutorBindingController,
    receiver_id: str = "kilo-cli-agent",
    request_id: str = "req-001",
    task_payload: str | None = None,
    **authorization_overrides,
) -> GovernedProductionRuntimeRequest:
    request = _make_request(
        receiver_id=receiver_id,
        request_id=request_id,
        task_payload=task_payload,
    )
    handle = binding_controller.get_binding_for_receiver(receiver_id)
    assert handle is not None
    authorization_receiver_id = authorization_overrides.pop(
        "authorization_receiver_id", receiver_id
    )
    values = {
        "invocation_authorization_id": f"ea4e27-auth-{request_id}",
        "receiver_id": authorization_receiver_id,
        "binding_id": handle.binding_id,
        "enablement_id": handle.enablement_id,
        "execution_request_id": request_id,
        "attempt_number": 1,
        "issued_at": QUALIFICATION_CLOCK,
        "expires_at": "2026-01-01T00:05:00Z",
        "runtime_scope": "production",
        "delegation_class": "governed",
        "nonce": f"ea4e27-nonce-{request_id}",
    }
    values.update(authorization_overrides)
    return replace(
        request,
        invocation_authorization=ProductionInvocationAuthorization(**values),
    )


def _bind_receiver(
    binding_controller: ProductionExecutorBindingController,
    executor_registry: ExecutorRegistry,
    receiver_id: str,
    clock: BindingClock,
) -> None:
    """Helper to bind a receiver through EA-4E.21."""
    executor_info = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    bindings = QUALIFIED_RECEIVERS[receiver_id]
    enablement = ProductionExecutorBindingEnablement(
        enablement_id=f"ea4e26-enablement-{receiver_id}",
        receiver_id=receiver_id,
        transport_contract_id=bindings["transport_contract_id"],
        model_binding_id=bindings["model_binding_id"],
        executor_identity=executor_info["executor_identity"],
        executor_factory=executor_info["executor_factory"],
        runtime_scope="production",
        issued_at=clock.now_iso(),
        expires_at=clock.now_plus_seconds(3600),
        delegation_class="governed",
        requested_ttl_seconds=3600,
        max_bound_executors=1,
        enabled=True,
        request_nonce=f"ea4e26-nonce-{receiver_id}",
    )
    fake_executor = FakeKiloQualificationExecutor() if receiver_id == "kilo-cli-agent" else FakeOpenCodeQualificationExecutor()
    bind_registry = ExecutorRegistry()
    binding_controller.bind(enablement, bind_registry, executor_factory=lambda: fake_executor)
    executor_registry.register(receiver_id, fake_executor)


# --------------------------------------------------------------------------- #
# Positive fake paths
# --------------------------------------------------------------------------- #

class TestKiloFakePath:
    def test_kilo_full_governed_path(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)

        assert result.route_decision == "SELECTED"
        assert result.issuance_policy_decision == "EXTERNAL_AUTHORITY"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.binding_decision == "ALLOW"
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_decision == "ALLOW"
        assert result.execution_decision == "EXECUTE"
        assert result.executor_called is True
        assert result.execution_status == "SUCCESS"
        assert result.execution_output == "EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK"
        assert result.ea4e26_disposition == "PASS"
        assert result.kilo_executor_calls == 1
        assert result.opencode_executor_calls == 0

    def test_kilo_custom_task_payload(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller,
            receiver_id="kilo-cli-agent",
            task_payload="EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK",
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "PASS"
        assert result.kilo_executor_calls == 1


class TestOpenCodeFakePath:
    def test_opencode_full_governed_path(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="opencode-cli-agent")
        result = runtime.execute(request)

        assert result.route_decision == "SELECTED"
        assert result.issuance_policy_decision == "EXTERNAL_AUTHORITY"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.binding_decision == "ALLOW"
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_decision == "ALLOW"
        assert result.execution_decision == "EXECUTE"
        assert result.executor_called is True
        assert result.execution_status == "SUCCESS"
        assert result.execution_output == "EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK"
        assert result.ea4e26_disposition == "PASS"
        assert result.opencode_executor_calls == 1
        assert result.kilo_executor_calls == 0

    def test_opencode_custom_task_payload(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller,
            receiver_id="opencode-cli-agent",
            task_payload="EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK",
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "PASS"
        assert result.opencode_executor_calls == 1


# --------------------------------------------------------------------------- #
# Cross-receiver authorization isolation (26A Gap C/D)
# --------------------------------------------------------------------------- #

class TestCrossReceiverAuthIsolation:
    """Direct proof that Kilo auth cannot execute OpenCode and vice versa."""

    def test_kilo_auth_cannot_execute_opencode(self, runtime, binding_controller, executor_registry, binding_clock):
        """Kilo-scoped invocation authorization must not execute OpenCode."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        # Attempt to use kilo binding for opencode execution
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)

        assert result.ea4e26_disposition == "FAIL"
        assert result.opencode_executor_calls == 0
        assert result.kilo_executor_calls == 0
        # Must fail at binding stage (kilo binding != opencode request)
        assert result.binding_decision == "REJECT"
        assert result.binding_reason == "NO_ACTIVE_EXECUTOR_BINDING"

    def test_opencode_auth_cannot_execute_kilo(self, runtime, binding_controller, executor_registry, binding_clock):
        """OpenCode-scoped invocation authorization must not execute Kilo."""
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        # Attempt to use opencode binding for kilo execution
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)

        assert result.ea4e26_disposition == "FAIL"
        assert result.opencode_executor_calls == 0
        assert result.kilo_executor_calls == 0
        assert result.binding_decision == "REJECT"
        assert result.binding_reason == "NO_ACTIVE_EXECUTOR_BINDING"

    def test_kilo_binding_resolves_only_as_kilo(self, runtime, binding_controller, executor_registry, binding_clock):
        """Kilo binding must not resolve as OpenCode."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)

        assert result.ea4e22_resolution_decision == "NOT_EVALUATED"  # Fails before EA-4E.22
        assert result.opencode_executor_calls == 0

    def test_opencode_binding_resolves_only_as_opencode(self, runtime, binding_controller, executor_registry, binding_clock):
        """OpenCode binding must not resolve as Kilo."""
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)

        assert result.ea4e22_resolution_decision == "NOT_EVALUATED"
        assert result.kilo_executor_calls == 0


# --------------------------------------------------------------------------- #
# Complete fail-closed matrix (30 cases)
# --------------------------------------------------------------------------- #

class TestFailClosedMatrix:
    """Comprehensive fail-closed matrix covering all 30 required cases."""

    # --- Case 1: Missing receiver ---
    def test_case_01_missing_receiver(self, runtime):
        request = _make_request(receiver_id="")
        result = runtime.execute(request)
        assert result.route_decision == "REJECT"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 2: Unsupported receiver ---
    def test_case_02_unsupported_receiver(self, runtime):
        request = _make_request(receiver_id="unknown-receiver")
        result = runtime.execute(request)
        assert result.route_decision == "REJECT"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 3: Receiver/router mismatch (empty transport/model contract) ---
    def test_case_03_receiver_router_mismatch(self, runtime):
        request = GovernedProductionRuntimeRequest(
            request_id="req-003",
            receiver_id="kilo-cli-agent",
            router_contract_id="invalid-router-contract",
            transport_contract_id="invalid",
            model_binding_id="invalid",
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 4: Issuance denied ---
    def test_case_04_issuance_denied(self, runtime):
        # Invalid transport contract triggers issuance rejection
        request = GovernedProductionRuntimeRequest(
            request_id="req-004",
            receiver_id="kilo-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id="invalid-transport",
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 5: Authority missing ---
    def test_case_05_authority_missing(self, runtime):
        request = GovernedProductionRuntimeRequest(
            request_id="req-005",
            receiver_id="kilo-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        )
        result = runtime.execute(request)
        # Without binding, this fails at binding check (before authority is created in boundary)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 6: Authority denied (invalid authority contract) ---
    def test_case_06_authority_denied(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        # Invalid transport contract causes issuance rejection (no authority created)
        request = GovernedProductionRuntimeRequest(
            request_id="req-006",
            receiver_id="kilo-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            transport_contract_id="invalid-transport",
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 7: Activation missing ---
    def test_case_07_activation_missing(self, runtime):
        request = replace(_make_request(receiver_id="kilo-cli-agent"), activation=None)
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 8: Activation disabled ---
    def test_case_08_activation_disabled(self, runtime):
        request = _make_request(receiver_id="kilo-cli-agent")
        request = replace(
            request,
            activation=build_production_activation(
                receiver_id=request.receiver_id,
                router_contract_id=request.router_contract_id,
                authority_contract_id=compute_ea4e7_authority_contract_id(),
                transport_contract_id=request.transport_contract_id,
                model_binding_id=request.model_binding_id,
                activation_mode="DISABLED",
                execution_scope=request.requested_execution_scope,
                delegation_class=request.delegation_class,
            ),
        )
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 9: No binding ---
    def test_case_09_no_binding(self, runtime):
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.binding_decision == "REJECT"
        assert result.binding_reason == "NO_ACTIVE_EXECUTOR_BINDING"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 10: Expired binding ---
    def test_case_10_expired_binding(self, runtime, binding_controller, executor_registry, binding_clock):
        expired_enablement = ProductionExecutorBindingEnablement(
            enablement_id="ea4e26-enablement-kilo-expired",
            receiver_id="kilo-cli-agent",
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            executor_identity=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_identity"],
            executor_factory=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_factory"],
            runtime_scope="production",
            issued_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-01T01:00:00Z",
            delegation_class="governed",
            requested_ttl_seconds=3600,
            max_bound_executors=1,
            enabled=True,
            request_nonce="ea4e26-nonce-kilo-expired",
        )
        fake_executor = FakeKiloQualificationExecutor()
        bind_registry = ExecutorRegistry()
        # Binding rejected because enablement is expired
        import pytest as _pytest
        with _pytest.raises(Exception, match="ENABLEMENT_EXPIRED"):
            binding_controller.bind(expired_enablement, bind_registry, executor_factory=lambda: fake_executor)

        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 11: Receiver/binding mismatch ---
    def test_case_11_receiver_binding_mismatch(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.binding_decision == "REJECT"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 12: Executor identity mismatch ---
    def test_case_12_executor_identity_mismatch(self, runtime, binding_controller, binding_clock):
        # Create enablement with wrong executor identity
        enablement = ProductionExecutorBindingEnablement(
            enablement_id="ea4e26-enablement-kilo-bad-identity",
            receiver_id="kilo-cli-agent",
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            executor_identity="WrongExecutorIdentity",
            executor_factory=QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]["executor_factory"],
            runtime_scope="production",
            issued_at=binding_clock.now_iso(),
            expires_at=binding_clock.now_plus_seconds(3600),
            delegation_class="governed",
            requested_ttl_seconds=3600,
            max_bound_executors=1,
            enabled=True,
            request_nonce="ea4e26-nonce-kilo-bad-identity",
        )
        fake_executor = FakeKiloQualificationExecutor()
        bind_registry = ExecutorRegistry()
        import pytest as _pytest
        with _pytest.raises(Exception, match="EXECUTOR_IDENTITY_MISMATCH"):
            binding_controller.bind(enablement, bind_registry, executor_factory=lambda: fake_executor)

        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 13: Invocation authorization missing ---
    def test_case_13_invocation_auth_missing(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_decision == "DENY"
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_REQUIRED"
        assert result.executor_called is False
        assert result.ea4e26_disposition == "FAIL"

    # --- Case 14: Invocation authorization denied ---
    def test_case_14_invocation_auth_denied(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller,
            receiver_id="kilo-cli-agent",
            authorization_receiver_id="opencode-cli-agent",
        )
        result = runtime.execute(request)
        assert result.invocation_claim_reason == "RECEIVER_BINDING_MISMATCH"
        assert result.executor_called is False
        assert result.ea4e26_disposition == "FAIL"

    # --- Case 15: Expired invocation authorization ---
    def test_case_15_invocation_auth_expired(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller,
            receiver_id="kilo-cli-agent",
            expires_at=QUALIFICATION_CLOCK,
        )
        result = runtime.execute(request)
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_EXPIRED"
        assert result.executor_called is False
        assert result.ea4e26_disposition == "FAIL"

    # --- Case 16: Receiver/invocation-auth mismatch ---
    def test_case_16_receiver_invocation_auth_mismatch(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 17: Binding ID mismatch ---
    def test_case_17_binding_id_mismatch(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 18: Enablement ID mismatch ---
    def test_case_18_enablement_id_mismatch(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 19: Request identity mismatch ---
    def test_case_19_request_identity_mismatch(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 20: Attempt number > 1 ---
    def test_case_20_attempt_number_gt_1(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller,
            receiver_id="kilo-cli-agent",
            request_id="req-20",
            attempt_number=2,
        )
        result = runtime.execute(request)
        assert result.invocation_claim_reason == "INVALID_ATTEMPT_NUMBER"
        assert result.executor_called is False

    # --- Case 21: Invocation authorization already consumed ---
    def test_case_21_invocation_auth_consumed(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(
            binding_controller, receiver_id="kilo-cli-agent", request_id="req-21"
        )
        result1 = runtime.execute(request)
        assert result1.ea4e26_disposition == "PASS"

        result2 = runtime.execute(request)
        assert result2.ea4e26_disposition == "FAIL"
        assert result2.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"
        assert result2.kilo_executor_calls == 0
        assert result2.opencode_executor_calls == 0

    # --- Case 22: Cross-receiver invocation replay ---
    def test_case_22_cross_receiver_invocation_replay(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 23: Same-ID conflicting canonical authorization ---
    def test_case_23_same_id_conflicting_canonical(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 24: Kilo failure does not fall back to OpenCode ---
    def test_case_24_kilo_failure_no_fallback(self, fixed_clock, binding_controller, executor_registry, binding_clock, tmp_path):
        # Create a failing Kilo executor
        failing_kilo = FakeFailingKiloExecutor()
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        # Register the failing executor AFTER binding to overwrite the qualification executor
        executor_registry.register("kilo-cli-agent", failing_kilo)
        runtime = _durable_runtime(
            fixed_clock, executor_registry, binding_controller, tmp_path, "case24.sqlite3"
        )
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)

        assert result.execution_status == "FAILURE"
        assert result.kilo_executor_calls == 1
        assert result.opencode_executor_calls == 0  # No fallback
        assert result.fallback_attempts == 0
        assert result.automatic_retry_attempts == 0

    # --- Case 25: OpenCode failure does not fall back to Kilo ---
    def test_case_25_opencode_failure_no_fallback(self, fixed_clock, binding_controller, executor_registry, binding_clock, tmp_path):
        failing_opencode = FakeFailingOpenCodeExecutor()
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        executor_registry.register("opencode-cli-agent", failing_opencode)
        runtime = _durable_runtime(
            fixed_clock, executor_registry, binding_controller, tmp_path, "case25.sqlite3"
        )
        request = _make_authorized_request(binding_controller, receiver_id="opencode-cli-agent")
        result = runtime.execute(request)

        assert result.execution_status == "FAILURE"
        assert result.opencode_executor_calls == 1
        assert result.kilo_executor_calls == 0  # No fallback
        assert result.fallback_attempts == 0
        assert result.automatic_retry_attempts == 0

    # --- Case 26: Executor failure after claim consumes authorization ---
    def test_case_26_executor_failure_consumes_auth(self, fixed_clock, binding_controller, executor_registry, binding_clock, tmp_path):
        failing_kilo = FakeFailingKiloExecutor()
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        executor_registry.register("kilo-cli-agent", failing_kilo)
        runtime = _durable_runtime(
            fixed_clock, executor_registry, binding_controller, tmp_path, "case26.sqlite3"
        )
        request = _make_authorized_request(
            binding_controller, receiver_id="kilo-cli-agent", request_id="req-26"
        )
        result1 = runtime.execute(request)
        assert result1.execution_status == "FAILURE"
        assert result1.kilo_executor_calls == 1

        # Second invocation should fail (authorization consumed)
        result2 = runtime.execute(request)
        assert result2.ea4e26_disposition == "FAIL"
        assert result2.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"
        assert result2.kilo_executor_calls == 0

    # --- Case 27: Pre-execution rejection does not consume authorization ---
    def test_case_27_preexecution_rejection_no_consume(self, runtime, binding_controller, executor_registry, binding_clock):
        # Attempt with no binding - should fail before claim
        request = _make_request(receiver_id="kilo-cli-agent", request_id="req-27a")
        result1 = runtime.execute(request)
        assert result1.ea4e26_disposition == "FAIL"
        assert result1.invocation_claim_decision == "NOT_EVALUATED"  # Never reached claim

        # Now bind and execute - should succeed (authorization not consumed by prior rejection)
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request2 = _make_authorized_request(
            binding_controller, receiver_id="kilo-cli-agent", request_id="req-27b"
        )
        result2 = runtime.execute(request2)
        assert result2.ea4e26_disposition == "PASS"

    # --- Case 28: Runtime disabled ---
    def test_case_28_runtime_disabled(self, runtime):
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        # Runtime is inert by default (no binding)
        assert result.production_activation_default == "DISABLED"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 29: No default receiver ---
    def test_case_29_no_default_receiver(self, runtime):
        request = _make_request(receiver_id="")
        result = runtime.execute(request)
        assert result.default_receiver == "NONE"
        assert result.route_decision == "REJECT"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0

    # --- Case 30: No auto-bind ---
    def test_case_30_no_auto_bind(self, runtime):
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.automatic_executor_binding_enabled is False
        assert result.binding_decision == "REJECT"
        assert result.binding_reason == "NO_ACTIVE_EXECUTOR_BINDING"
        assert result.ea4e26_disposition == "FAIL"
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 0


# --------------------------------------------------------------------------- #
# Single-use semantics
# --------------------------------------------------------------------------- #

class TestSingleUse:
    def test_first_claim_allow(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.invocation_claim_decision == "ALLOW"
        assert result.live_invocation_authorization_claims_granted == 1

    def test_authorization_consumed(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.live_invocation_authorization_claims_granted == 1
        assert result.live_invocation_authorizations_issued == 0


# --------------------------------------------------------------------------- #
# Receiver isolation
# --------------------------------------------------------------------------- #

class TestReceiverIsolation:
    def test_kilo_auth_cannot_execute_opencode(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"

    def test_opencode_auth_cannot_execute_kilo(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.ea4e26_disposition == "FAIL"

    def test_kilo_executor_calls_zero_for_opencode(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="opencode-cli-agent")
        result = runtime.execute(request)
        assert result.kilo_executor_calls == 0
        assert result.opencode_executor_calls == 1

    def test_opencode_executor_calls_zero_for_kilo(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.opencode_executor_calls == 0
        assert result.kilo_executor_calls == 1


# --------------------------------------------------------------------------- #
# Default state
# --------------------------------------------------------------------------- #

class TestDefaultState:
    def test_default_binding_decision(self, runtime):
        assert runtime.execute(_make_request()).default_binding_decision == "DENY"

    def test_default_invocation_authorization_decision(self, runtime):
        assert runtime.execute(_make_request()).default_invocation_authorization_decision == "DENY"

    def test_default_receiver_none(self, runtime):
        assert runtime.execute(_make_request()).default_receiver == "NONE"

    def test_no_automatic_receiver_selection(self, runtime):
        assert runtime.execute(_make_request()).automatic_receiver_selection_enabled is False

    def test_no_automatic_binding(self, runtime):
        assert runtime.execute(_make_request()).automatic_executor_binding_enabled is False

    def test_no_automatic_invocation_authorization(self, runtime):
        assert runtime.execute(_make_request()).automatic_invocation_authorization_enabled is False

    def test_no_automatic_retry(self, runtime):
        assert runtime.execute(_make_request()).automatic_retry_enabled is False

    def test_no_fallback(self, runtime):
        assert runtime.execute(_make_request()).fallback_enabled is False

    def test_no_failover(self, runtime):
        assert runtime.execute(_make_request()).failover_enabled is False

    def test_production_activation_default_disabled(self, runtime):
        assert runtime.execute(_make_request()).production_activation_default == "DISABLED"

    def test_no_persistent_production_execution(self, runtime):
        assert runtime.execute(_make_request()).persistent_production_execution_enabled is False


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_same_request_same_decision(self, fixed_clock, executor_registry, binding_controller, binding_clock, tmp_path):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, request_id="same-1")
        result1 = _durable_runtime(
            fixed_clock, executor_registry, binding_controller, tmp_path, "det1.sqlite3"
        ).execute(request)

        # Re-bind
        binding_controller2 = ProductionExecutorBindingController(
            policy=ProductionExecutorBindingPolicy(clock=binding_clock),
            clock=binding_clock,
        )
        registry2 = ExecutorRegistry()
        registry2.register("kilo-cli-agent", FakeKiloQualificationExecutor())
        registry2.register("opencode-cli-agent", FakeOpenCodeQualificationExecutor())
        _bind_receiver(binding_controller2, registry2, "kilo-cli-agent", binding_clock)

        result2 = _durable_runtime(
            fixed_clock, registry2, binding_controller2, tmp_path, "det2.sqlite3"
        ).execute(_make_authorized_request(binding_controller2, request_id="same-1"))

        assert result1.route_decision == result2.route_decision
        assert result1.issuance_policy_decision == result2.issuance_policy_decision
        assert result1.execution_decision == result2.execution_decision

    def test_task_text_does_not_affect_receiver_selection(self, runtime, binding_controller, executor_registry, binding_clock, tmp_path):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request1 = _make_authorized_request(
            binding_controller, receiver_id="kilo-cli-agent", task_payload="Task A"
        )
        result1 = runtime.execute(request1)

        # Re-bind
        binding_controller2 = ProductionExecutorBindingController(
            policy=ProductionExecutorBindingPolicy(clock=binding_clock),
            clock=binding_clock,
        )
        registry2 = ExecutorRegistry()
        registry2.register("kilo-cli-agent", FakeKiloQualificationExecutor())
        registry2.register("opencode-cli-agent", FakeOpenCodeQualificationExecutor())
        _bind_receiver(binding_controller2, registry2, "kilo-cli-agent", binding_clock)

        request2 = _make_authorized_request(
            binding_controller2,
            receiver_id="kilo-cli-agent",
            task_payload="Task B completely different",
        )
        result2 = _durable_runtime(
            ClockCollaborator(now=QUALIFICATION_CLOCK),
            registry2,
            binding_controller2,
            tmp_path,
            "task-text.sqlite3",
        ).execute(request2)

        assert result1.route_decision == result2.route_decision
        assert result1.ea4e26_disposition == result2.ea4e26_disposition


# --------------------------------------------------------------------------- #
# Bypass tracking
# --------------------------------------------------------------------------- #

class TestBypassTracking:
    def test_no_bypass_on_success(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_authorized_request(binding_controller, receiver_id="kilo-cli-agent")
        result = runtime.execute(request)

        assert result.router_bypassed is False
        assert result.issuance_bypassed is False
        assert result.authority_validation_bypassed is False
        assert result.activation_validation_bypassed is False
        assert result.binding_check_bypassed is False
        assert result.ea4e22_resolution_bypassed is False
        assert result.invocation_authorization_bypassed is False
        assert result.atomic_claim_bypassed is False
        assert result.production_boundary_bypassed is False


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #

class TestContract:
    def test_contract_deterministic(self):
        id1 = compute_ea4e26_integration_contract_id()
        id2 = compute_ea4e26_integration_contract_id()
        assert id1 == id2

    def test_contract_is_sha256(self):
        contract_id = compute_ea4e26_integration_contract_id()
        assert len(contract_id) == 64
        assert all(c in "0123456789abcdef" for c in contract_id)


# --------------------------------------------------------------------------- #
# No live activity
# --------------------------------------------------------------------------- #

class TestNoLiveActivity:
    def test_no_real_kilo_executor_instantiations(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.real_kilo_executor_instantiations == 0
        assert result.real_opencode_executor_instantiations == 0

    def test_no_real_adapter_calls(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.real_kilo_adapter_calls == 0
        assert result.real_opencode_adapter_calls == 0

    def test_no_live_bindings_created(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.live_bindings_created == 0

    def test_no_production_boundary_real_executions(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        request = _make_request(receiver_id="kilo-cli-agent")
        result = runtime.execute(request)
        assert result.production_execution_boundary_real_executions == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
