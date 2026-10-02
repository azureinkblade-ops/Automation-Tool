"""EA-4E.14 production execution boundary tests."""

from __future__ import annotations

import pytest

from tools.hermes_core.production_execution import (
    ExecutorRegistry,
    FakeKiloExecutor,
    FakeOpenCodeExecutor,
    ProductionExecutionBoundary,
    ProductionExecutionRequest,
)
from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import build_production_activation


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def registry():
    reg = ExecutorRegistry()
    reg.register("kilo-cli-agent", FakeKiloExecutor())
    reg.register("opencode-cli-agent", FakeOpenCodeExecutor())
    return reg


@pytest.fixture
def boundary(registry):
    return ProductionExecutionBoundary(executor_registry=registry)


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
        delegation_id="delegation-001",
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=bindings.get("transport_contract_id", "unknown"),
        model_binding_id=bindings.get("model_binding_id", "unknown"),
        execution_scope="production",
        task_payload="test task",
        attempt_limit=attempt_limit,
    )


# --------------------------------------------------------------------------- #
# Positive cases
# --------------------------------------------------------------------------- #

class TestPositiveCases:
    def test_kilo_fake_execution(self, boundary):
        auth = _build_auth("kilo-cli-agent", "kilo-fake")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")

        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )

        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.execution_decision == "EXECUTE"
        assert result.adapter_resolution == "KILO"
        assert result.executor_called is True
        assert result.executor_id == "fake-kilo-executor"
        assert result.execution_status == "SUCCESS"
        assert result.executor_output == "EA4E14_KILO_FAKE_EXECUTION_OK"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False

    def test_opencode_fake_execution(self, boundary):
        auth = _build_auth("opencode-cli-agent", "opencode-fake")
        activation = _build_activation("opencode-cli-agent", "ENABLED")
        request = _build_request("opencode-cli-agent")

        result = boundary.execute(
            receiver_id="opencode-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )

        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.execution_decision == "EXECUTE"
        assert result.adapter_resolution == "OPENCODE"
        assert result.executor_called is True
        assert result.executor_id == "fake-opencode-executor"
        assert result.execution_status == "SUCCESS"
        assert result.executor_output == "EA4E14_OPENCODE_FAKE_EXECUTION_OK"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False


# --------------------------------------------------------------------------- #
# Fail-closed cases
# --------------------------------------------------------------------------- #

class TestFailClosed:
    def test_missing_receiver(self, boundary):
        result = boundary.execute(
            receiver_id="",
            authority=None,
            activation=None,
            execution_request=_build_request(""),
        )
        assert result.execution_decision == "REJECT"
        assert result.executor_called is False
        assert result.route_decision == "REJECT"

    def test_unsupported_receiver(self, boundary):
        result = boundary.execute(
            receiver_id="unknown",
            authority=None,
            activation=None,
            execution_request=_build_request("unknown"),
        )
        assert result.execution_decision == "REJECT"
        assert result.executor_called is False
        assert result.route_decision == "REJECT"

    def test_missing_authority(self, boundary):
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=None,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_MISSING"
        assert result.executor_called is False

    def test_denied_authority(self, boundary):
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
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=denied_auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_DENIED"
        assert result.executor_called is False

    def test_missing_activation(self, boundary):
        auth = _build_auth("kilo-cli-agent", "missing-act")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=None,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "PRODUCTION_ACTIVATION_MISSING"
        assert result.executor_called is False

    def test_disabled_activation(self, boundary):
        auth = _build_auth("kilo-cli-agent", "disabled-act")
        activation = _build_activation("kilo-cli-agent", "DISABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "PRODUCTION_ACTIVATION_DISABLED"
        assert result.executor_called is False

    def test_authority_receiver_mismatch(self, boundary):
        wrong_auth = _build_auth("opencode-cli-agent", "mismatch")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=wrong_auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "AUTHORITY_RECEIVER_MISMATCH"
        assert result.executor_called is False

    def test_activation_receiver_mismatch(self, boundary):
        auth = _build_auth("kilo-cli-agent", "act-mismatch")
        wrong_activation = _build_activation("opencode-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=wrong_activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "ACTIVATION_RECEIVER_MISMATCH"
        assert result.executor_called is False

    def test_router_contract_mismatch(self, boundary):
        auth = _build_auth("kilo-cli-agent", "router-mm")
        activation = _build_activation("kilo-cli-agent", "ENABLED", router_contract_id="wrong")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "ROUTER_CONTRACT_MISMATCH"
        assert result.executor_called is False

    def test_authority_contract_mismatch(self, boundary):
        auth = _build_auth("kilo-cli-agent", "auth-mm")
        activation = _build_activation("kilo-cli-agent", "ENABLED", authority_contract_id="wrong")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "AUTHORITY_CONTRACT_MISMATCH"
        assert result.executor_called is False

    def test_transport_mismatch(self, boundary):
        auth = _build_auth("kilo-cli-agent", "transport-mm")
        activation = _build_activation("kilo-cli-agent", "ENABLED", transport_contract_id="wrong")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "TRANSPORT_CONTRACT_MISMATCH"
        assert result.executor_called is False

    def test_model_binding_mismatch(self, boundary):
        auth = _build_auth("kilo-cli-agent", "model-mm")
        activation = _build_activation("kilo-cli-agent", "ENABLED", model_binding_id="wrong")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "MODEL_BINDING_MISMATCH"
        assert result.executor_called is False

    def test_missing_executor(self):
        """No executor registered for kilo."""
        reg = ExecutorRegistry()
        boundary = ProductionExecutionBoundary(executor_registry=reg)
        auth = _build_auth("kilo-cli-agent", "no-exec")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "EXECUTOR_NOT_CONFIGURED"
        assert result.executor_called is False

    def test_execution_budget_exhausted(self, boundary):
        auth = _build_auth("kilo-cli-agent", "budget")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent", attempt_limit=0)
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.execution_decision == "REJECT"
        assert result.reason == "EXECUTION_BUDGET_EXHAUSTED"
        assert result.executor_called is False


# --------------------------------------------------------------------------- #
# No fallback
# --------------------------------------------------------------------------- #

class TestNoFallback:
    def test_kilo_rejection_does_not_route_to_opencode(self, boundary):
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=None,
            activation=None,
            execution_request=_build_request("kilo-cli-agent"),
        )
        assert result.execution_decision == "REJECT"
        assert result.receiver_id == "kilo-cli-agent"

    def test_opencode_rejection_does_not_route_to_kilo(self, boundary):
        result = boundary.execute(
            receiver_id="opencode-cli-agent",
            authority=None,
            activation=None,
            execution_request=_build_request("opencode-cli-agent"),
        )
        assert result.execution_decision == "REJECT"
        assert result.receiver_id == "opencode-cli-agent"


# --------------------------------------------------------------------------- #
# No execution
# --------------------------------------------------------------------------- #

class TestNoExecution:
    def test_no_real_adapter_call(self, boundary):
        auth = _build_auth("kilo-cli-agent", "no-real")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.real_adapter_called is False

    def test_no_process_start(self, boundary):
        auth = _build_auth("kilo-cli-agent", "no-proc")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.process_started is False

    def test_no_model_invocation(self, boundary):
        auth = _build_auth("kilo-cli-agent", "no-model")
        activation = _build_activation("kilo-cli-agent", "ENABLED")
        request = _build_request("kilo-cli-agent")
        result = boundary.execute(
            receiver_id="kilo-cli-agent",
            authority=auth,
            activation=activation,
            execution_request=request,
        )
        assert result.model_invoked is False
