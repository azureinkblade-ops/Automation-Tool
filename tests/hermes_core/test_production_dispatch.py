"""EA-4E.8 production-path integration tests."""

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
from tools.hermes_core.production_dispatch import (
    ProductionDispatchRequest,
    ReceiverDispatchCoordinator,
    get_default_coordinator,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def coordinator():
    return get_default_coordinator()


def _build_valid_authority(
    *,
    receiver_id: str,
    decision: str = "GRANTED",
    transport_contract_id: str | None = None,
    model_binding_id: str | None = None,
    router_contract_id: str | None = None,
    expires_at: str = "2099-01-01T00:00:00Z",
):
    """Helper to build a valid authority for the given receiver."""
    bindings = QUALIFIED_RECEIVERS.get(receiver_id, {})
    return build_dispatch_authority(
        receiver_id=receiver_id,
        transport_contract_id=transport_contract_id or bindings.get("transport_contract_id", ""),
        model_binding_id=model_binding_id or bindings.get("model_binding_id", ""),
        router_contract_id=router_contract_id or compute_ea4e6_router_contract_id(),
        scope=DispatchAuthorityScope(
            operation="receiver-dispatch",
            receiver_id=receiver_id,
        ),
        delegation_class="governed",
        decision=decision,
        issued_at="2026-01-01T00:00:00Z",
        expires_at=expires_at,
        nonce="prod-nonce-001",
    )


# --------------------------------------------------------------------------- #
# Positive production-path cases
# --------------------------------------------------------------------------- #

class TestProductionPathPositive:
    """Prove production-path integration for both qualified receivers."""

    def test_opencode_production_fake(self, coordinator):
        """OpenCode production-path fake dispatch."""
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="opencode-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.route_decision == "SELECTED"
        assert result.receiver_id == "opencode-cli-agent"
        assert result.authority_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.production_path_integration == "PASS"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.receiver_executed is False

    def test_kilo_production_fake(self, coordinator):
        """Kilo production-path fake dispatch."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.route_decision == "SELECTED"
        assert result.receiver_id == "kilo-cli-agent"
        assert result.authority_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.production_path_integration == "PASS"
        assert result.real_adapter_called is False
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.receiver_executed is False


# --------------------------------------------------------------------------- #
# Fail-closed production-path cases
# --------------------------------------------------------------------------- #

class TestProductionPathFailClosed:
    """Prove production-path fail-closed behavior."""

    def test_missing_receiver_id(self, coordinator):
        request = ProductionDispatchRequest(receiver_id="")
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EMPTY_RECEIVER_ID"
        assert result.process_started is False

    def test_unsupported_receiver(self, coordinator):
        request = ProductionDispatchRequest(receiver_id="unknown-receiver")
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "UNSUPPORTED_RECEIVER"
        assert result.process_started is False

    def test_missing_authority(self, coordinator):
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=None,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_MISSING"
        assert result.process_started is False

    def test_denied_authority(self, coordinator):
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            decision="DENIED",
        )
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_DENIED"
        assert result.process_started is False

    def test_receiver_mismatch(self, coordinator):
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "AUTHORITY_RECEIVER_MISMATCH"
        assert result.process_started is False

    def test_router_contract_mismatch(self, coordinator):
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            router_contract_id="wrong-router-contract",
        )
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "ROUTER_CONTRACT_MISMATCH"
        assert result.process_started is False

    def test_transport_contract_mismatch(self, coordinator):
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            transport_contract_id="wrong-transport",
        )
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "TRANSPORT_CONTRACT_MISMATCH"
        assert result.process_started is False

    def test_model_binding_mismatch(self, coordinator):
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            model_binding_id="wrong-model",
        )
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MODEL_BINDING_MISMATCH"
        assert result.process_started is False

    def test_malformed_authority(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        object.__setattr__(authority, "artifact_hash", "tampered")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MALFORMED_AUTHORITY"
        assert result.process_started is False

    def test_expired_authority(self, coordinator):
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            expires_at="2020-01-01T00:05:00Z",
        )
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "AUTHORITY_EXPIRED"
        assert result.process_started is False


# --------------------------------------------------------------------------- #
# No fallback
# --------------------------------------------------------------------------- #

class TestNoFallback:
    """Prove no fallback/failover behavior."""

    def test_kilo_rejection_does_not_route_to_opencode(self, coordinator):
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=None,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.receiver_id == "kilo-cli-agent"

    def test_opencode_rejection_does_not_route_to_kilo(self, coordinator):
        request = ProductionDispatchRequest(
            receiver_id="opencode-cli-agent",
            execution_authority=None,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "REJECT"
        assert result.receiver_id == "opencode-cli-agent"


# --------------------------------------------------------------------------- #
# Execution boundary
# --------------------------------------------------------------------------- #

class TestExecutionBoundary:
    """Prove execution-authority separation."""

    def test_router_creates_no_execution_authority(self, coordinator):
        request = ProductionDispatchRequest(receiver_id="kilo-cli-agent")
        result = coordinator.dispatch(request)
        assert result.authority_valid is False

    def test_production_integration_creates_no_authority(self, coordinator):
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=None,
        )
        result = coordinator.dispatch(request)
        assert result.authority_valid is False

    def test_route_selected_not_execution_authorized(self, coordinator):
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=None,
        )
        result = coordinator.dispatch(request)
        assert result.route_decision == "SELECTED"
        assert result.dispatch_decision == "REJECT"

    def test_execution_authorized_not_receiver_executed(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.receiver_executed is False

    def test_production_path_reached_not_receiver_executed(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.production_path_integration == "PASS"
        assert result.receiver_executed is False


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    """Prove deterministic behavior."""

    def test_same_request_same_result(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        r1 = coordinator.dispatch(request)
        r2 = coordinator.dispatch(request)
        assert r1 == r2

    def test_cross_instance_determinism(self):
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="opencode-cli-agent",
            execution_authority=authority,
        )
        c1 = ReceiverDispatchCoordinator()
        c2 = ReceiverDispatchCoordinator()
        r1 = c1.dispatch(request)
        r2 = c2.dispatch(request)
        assert r1 == r2

    def test_coordinator_contract_id_reproducible(self):
        from tools.hermes_core.production_dispatch import compute_ea4e8_coordinator_contract_id
        assert compute_ea4e8_coordinator_contract_id() == compute_ea4e8_coordinator_contract_id()


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


# --------------------------------------------------------------------------- #
# No execution
# --------------------------------------------------------------------------- #

class TestNoExecution:
    """Prove no real execution occurs."""

    def test_no_process_start(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.process_started is False

    def test_no_model_invocation(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.model_invoked is False

    def test_no_real_adapter_call(self, coordinator):
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        request = ProductionDispatchRequest(
            receiver_id="kilo-cli-agent",
            execution_authority=authority,
        )
        result = coordinator.dispatch(request)
        assert result.real_adapter_called is False
