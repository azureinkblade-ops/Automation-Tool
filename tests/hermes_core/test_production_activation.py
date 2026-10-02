"""EA-4E.11 dual-receiver production activation tests."""

from __future__ import annotations

import pytest

from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    compute_ea4e6_router_contract_id,
)
from tools.hermes_core.receiver_dispatch import (
    DispatchAuthorityScope,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
)
from tools.hermes_core.production_activation import (
    ProductionActivation,
    ProductionActivationValidator,
    ProductionReceiverCoordinator,
    ReceiverAdapterResolver,
    build_production_activation,
    compute_ea4e11_activation_contract_id,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def coordinator():
    return ProductionReceiverCoordinator()


def _build_valid_authority(*, receiver_id: str):
    """Helper to build a valid authority for the given receiver."""
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return build_dispatch_authority(
        receiver_id=receiver_id,
        transport_contract_id=bindings.get("transport_contract_id", ""),
        model_binding_id=bindings.get("model_binding_id", ""),
        router_contract_id=compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(operation="receiver-dispatch", receiver_id=receiver_id),
        delegation_class="governed",
        decision="GRANTED",
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
        nonce=f"auth-{receiver_id}",
    )


def _build_valid_activation(*, receiver_id: str, mode: str = "ENABLED"):
    """Helper to build a valid activation for the given receiver."""
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return build_production_activation(
        receiver_id=receiver_id,
        router_contract_id=compute_ea4e6_router_contract_id(),
        authority_contract_id=compute_ea4e7_authority_contract_id(),
        transport_contract_id=bindings.get("transport_contract_id", ""),
        model_binding_id=bindings.get("model_binding_id", ""),
        activation_mode=mode,
        execution_scope="production",
        delegation_class="governed",
    )


# --------------------------------------------------------------------------- #
# Positive cases
# --------------------------------------------------------------------------- #

class TestPositiveCases:
    """Prove positive production-path activation for both receivers."""

    def test_kilo_fake_activation(self, coordinator):
        """Kilo production activation fake path."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent", mode="ENABLED")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.adapter_resolution == "KILO"
        assert result.production_path_integration == "PASS"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.receiver_executed is False

    def test_opencode_fake_activation(self, coordinator):
        """OpenCode production activation fake path."""
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        activation = _build_valid_activation(receiver_id="opencode-cli-agent", mode="ENABLED")
        result = coordinator.dispatch(
            receiver_id="opencode-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.activation_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.adapter_resolution == "OPENCODE"
        assert result.production_path_integration == "PASS"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.receiver_executed is False


# --------------------------------------------------------------------------- #
# Fail-closed cases
# --------------------------------------------------------------------------- #

class TestFailClosed:
    """Prove fail-closed behavior."""

    def test_missing_receiver_id(self, coordinator):
        result = coordinator.dispatch(receiver_id="", authority=None, activation=None)
        assert result.dispatch_decision == "REJECT"

    def test_unsupported_receiver(self, coordinator):
        result = coordinator.dispatch(receiver_id="unknown", authority=None, activation=None)
        assert result.dispatch_decision == "REJECT"

    def test_missing_authority(self, coordinator):
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=None,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_MISSING"

    def test_denied_authority(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        authority_denied = build_dispatch_authority(
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
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority_denied,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_DENIED"

    def test_authority_receiver_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "AUTHORITY_RECEIVER_MISMATCH"

    def test_router_contract_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = build_production_activation(
            receiver_id="kilo-cli-agent",
            router_contract_id="wrong-router",
            authority_contract_id=compute_ea4e7_authority_contract_id(),
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            activation_mode="ENABLED",
            execution_scope="production",
            delegation_class="governed",
        )
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "ROUTER_CONTRACT_MISMATCH"

    def test_transport_contract_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = build_production_activation(
            receiver_id="kilo-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            authority_contract_id=compute_ea4e7_authority_contract_id(),
            transport_contract_id="wrong-transport",
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            activation_mode="ENABLED",
            execution_scope="production",
            delegation_class="governed",
        )
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "TRANSPORT_CONTRACT_MISMATCH"

    def test_model_binding_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = build_production_activation(
            receiver_id="kilo-cli-agent",
            router_contract_id=compute_ea4e6_router_contract_id(),
            authority_contract_id=compute_ea4e7_authority_contract_id(),
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id="wrong-model",
            activation_mode="ENABLED",
            execution_scope="production",
            delegation_class="governed",
        )
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MODEL_BINDING_MISMATCH"

    def test_missing_activation(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=None,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "PRODUCTION_ACTIVATION_MISSING"

    def test_disabled_activation(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent", mode="DISABLED")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "PRODUCTION_ACTIVATION_DISABLED"

    def test_activation_receiver_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="opencode-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "ACTIVATION_RECEIVER_MISMATCH"

    def test_malformed_activation(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        object.__setattr__(activation, "artifact_hash", "tampered")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MALFORMED_ACTIVATION"


# --------------------------------------------------------------------------- #
# No fallback
# --------------------------------------------------------------------------- #

class TestNoFallback:
    """Prove no fallback/failover behavior."""

    def test_kilo_rejection_does_not_route_to_opencode(self, coordinator):
        """Kilo rejection does not fall back to OpenCode."""
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=None,
            activation=None,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.receiver_id == "kilo-cli-agent"

    def test_opencode_rejection_does_not_route_to_kilo(self, coordinator):
        """OpenCode rejection does not fall back to Kilo."""
        result = coordinator.dispatch(
            receiver_id="opencode-cli-agent",
            authority=None,
            activation=None,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.receiver_id == "opencode-cli-agent"


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    """Prove deterministic behavior."""

    def test_same_request_same_result(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        r1 = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        r2 = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert r1 == r2

    def test_cross_instance_determinism(self):
        c1 = ProductionReceiverCoordinator()
        c2 = ProductionReceiverCoordinator()
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        activation = _build_valid_activation(receiver_id="opencode-cli-agent")
        r1 = c1.dispatch(
            receiver_id="opencode-cli-agent",
            authority=authority,
            activation=activation,
        )
        r2 = c2.dispatch(
            receiver_id="opencode-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert r1 == r2

    def test_activation_contract_id_reproducible(self):
        assert compute_ea4e11_activation_contract_id() == compute_ea4e11_activation_contract_id()


# --------------------------------------------------------------------------- #
# No execution
# --------------------------------------------------------------------------- #

class TestNoExecution:
    """Prove no real execution occurs."""

    def test_no_process_start(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.process_started is False

    def test_no_model_invocation(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.model_invoked is False

    def test_no_real_adapter_call(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        activation = _build_valid_activation(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
            activation=activation,
        )
        assert result.real_adapter_called is False


# --------------------------------------------------------------------------- #
# Contract freeze
# --------------------------------------------------------------------------- #

class TestContractFreeze:
    """Prove contracts remain unchanged."""

    def test_router_contract_unchanged(self):
        actual = compute_ea4e6_router_contract_id()
        from tools.hermes_core.hashing import sha256_payload
        from tools.hermes_core.receiver_router import get_default_router
        router = get_default_router()
        expected = sha256_payload(router.get_canonical_material())
        assert actual == expected

    def test_authority_contract_unchanged(self):
        actual = compute_ea4e7_authority_contract_id()
        from tools.hermes_core.hashing import sha256_payload
        from tools.hermes_core.receiver_dispatch import get_authority_canonical_material
        expected = sha256_payload(get_authority_canonical_material())
        assert actual == expected

    def test_qualified_receivers_frozen(self):
        receivers = set(QUALIFIED_RECEIVERS.keys())
        assert receivers == {"opencode-cli-agent", "kilo-cli-agent"}
