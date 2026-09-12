"""EA-4E.7 execution-authority integration tests."""

from __future__ import annotations

import pytest

from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
)
from tools.hermes_core.receiver_dispatch import (
    AUTHORITY_ARTIFACT_VERSION,
    AUTHORITY_SCHEMA_ID,
    AUTHORITY_SCHEMA_VERSION,
    DispatchAuthority,
    DispatchAuthorityScope,
    DispatchDecision,
    ExecutionAuthorityValidator,
    FakeDispatchLayer,
    build_dispatch_authority,
    compute_ea4e7_authority_contract_id,
    get_authority_canonical_material,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def router():
    return get_default_router()


@pytest.fixture
def dispatch_layer():
    return FakeDispatchLayer()


def _build_valid_authority(
    *,
    receiver_id: str,
    decision: str = "GRANTED",
    transport_contract_id: str | None = None,
    model_binding_id: str | None = None,
    router_contract_id: str | None = None,
) -> DispatchAuthority:
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
        expires_at="2099-01-01T00:00:00Z",
        nonce="test-nonce-001",
    )


# --------------------------------------------------------------------------- #
# Positive fake authorization cases
# --------------------------------------------------------------------------- #

class TestPositiveFakeAuthorization:
    """Prove fake authorization for both qualified receivers."""

    def test_opencode_fake_authorization(self, dispatch_layer):
        """OpenCode is authorized when authority is valid."""
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        result = dispatch_layer.dispatch(
            receiver_id="opencode-cli-agent",
            authority=authority,
        )
        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.dispatch_started is False

    def test_kilo_fake_authorization(self, dispatch_layer):
        """Kilo is authorized when authority is valid."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.route_decision == "SELECTED"
        assert result.authority_valid is True
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.process_started is False
        assert result.model_invoked is False
        assert result.dispatch_started is False


# --------------------------------------------------------------------------- #
# Fail-closed cases
# --------------------------------------------------------------------------- #

class TestFailClosed:
    """Prove fail-closed behavior for all rejection paths."""

    def test_missing_authority(self, dispatch_layer):
        """Missing authority rejects dispatch."""
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=None,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_MISSING"
        assert result.process_started is False

    def test_denied_authority(self, dispatch_layer):
        """Denied authority rejects dispatch."""
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            decision="DENIED",
        )
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "EXECUTION_AUTHORITY_DENIED"
        assert result.process_started is False

    def test_receiver_mismatch(self, dispatch_layer):
        """Authority for different receiver rejects dispatch."""
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "AUTHORITY_RECEIVER_MISMATCH"
        assert result.process_started is False

    def test_router_contract_mismatch(self, dispatch_layer):
        """Wrong router contract rejects dispatch."""
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            router_contract_id="wrong-router-contract",
        )
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "ROUTER_CONTRACT_MISMATCH"
        assert result.process_started is False

    def test_transport_contract_mismatch(self, dispatch_layer):
        """Wrong transport contract rejects dispatch."""
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            transport_contract_id="wrong-transport-contract",
        )
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "TRANSPORT_CONTRACT_MISMATCH"
        assert result.process_started is False

    def test_model_binding_mismatch(self, dispatch_layer):
        """Wrong model binding rejects dispatch."""
        authority = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            model_binding_id="wrong-model-binding",
        )
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MODEL_BINDING_MISMATCH"
        assert result.process_started is False

    def test_unsupported_receiver(self, dispatch_layer):
        """Unsupported receiver is rejected."""
        result = dispatch_layer.dispatch(
            receiver_id="unknown-receiver",
            authority=None,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "ROUTE_NOT_SELECTED"
        assert result.process_started is False

    def test_malformed_authority(self, dispatch_layer):
        """Authority with wrong hash is rejected."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        # Tamper with the hash
        object.__setattr__(authority, "artifact_hash", "tampered-hash")
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "MALFORMED_AUTHORITY"
        assert result.process_started is False

    def test_expired_authority(self, dispatch_layer):
        """Expired authority is rejected."""
        authority = build_dispatch_authority(
            receiver_id="kilo-cli-agent",
            transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
            model_binding_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["model_binding_id"],
            router_contract_id=compute_ea4e6_router_contract_id(),
            scope=DispatchAuthorityScope(
                operation="receiver-dispatch",
                receiver_id="kilo-cli-agent",
            ),
            delegation_class="governed",
            decision="GRANTED",
            issued_at="2020-01-01T00:00:00Z",
            expires_at="2020-01-01T00:05:00Z",
            nonce="expired-nonce",
        )
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "REJECT"
        assert result.reason == "AUTHORITY_EXPIRED"
        assert result.process_started is False


# --------------------------------------------------------------------------- #
# Execution boundary
# --------------------------------------------------------------------------- #

class TestExecutionBoundary:
    """Prove execution-authority separation."""

    def test_router_creates_no_execution_authority(self):
        """Router does not create execution authority."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        assert result.execution_started is False
        assert result.execution_authority_present is False

    def test_authority_validation_starts_no_receiver(self):
        """Authority validation does not start a receiver."""
        validator = ExecutionAuthorityValidator(
            router_contract_id=compute_ea4e6_router_contract_id(),
        )
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        route_result = get_default_router().route(RoutingRequest(receiver_id="kilo-cli-agent"))
        result = validator.validate(authority, route_result)
        assert result.process_started is False

    def test_fake_dispatch_starts_no_receiver(self):
        """Fake dispatch does not start a receiver."""
        dispatch_layer = FakeDispatchLayer()
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.process_started is False
        assert result.dispatch_started is False

    def test_route_selected_not_execution_authorized(self):
        """ROUTE_SELECTED != EXECUTION_AUTHORIZED."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        assert result.route_decision == "SELECTED"
        # Router does not set execution_authority_present=True
        assert result.execution_authority_present is False

    def test_execution_authorized_not_process_started(self):
        """EXECUTION_AUTHORIZED != PROCESS_STARTED."""
        dispatch_layer = FakeDispatchLayer()
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = dispatch_layer.dispatch(
            receiver_id="kilo-cli-agent",
            authority=authority,
        )
        assert result.dispatch_decision == "AUTHORIZED"
        assert result.process_started is False


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

class TestDeterminism:
    """Prove deterministic behavior."""

    def test_same_input_same_output(self, dispatch_layer):
        """Same inputs produce same dispatch decision."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        r1 = dispatch_layer.dispatch(receiver_id="kilo-cli-agent", authority=authority)
        r2 = dispatch_layer.dispatch(receiver_id="kilo-cli-agent", authority=authority)
        assert r1 == r2

    def test_cross_instance_determinism(self):
        """Two dispatch layers produce identical results."""
        authority = _build_valid_authority(receiver_id="opencode-cli-agent")
        dl1 = FakeDispatchLayer()
        dl2 = FakeDispatchLayer()
        r1 = dl1.dispatch(receiver_id="opencode-cli-agent", authority=authority)
        r2 = dl2.dispatch(receiver_id="opencode-cli-agent", authority=authority)
        assert r1 == r2

    def test_authority_contract_id_reproducible(self):
        """Authority contract ID is deterministic."""
        assert compute_ea4e7_authority_contract_id() == compute_ea4e7_authority_contract_id()

    def test_changing_receiver_contract_invalidates(self):
        """Changing any bound contract value invalidates authorization."""
        # Valid authority
        valid = _build_valid_authority(receiver_id="kilo-cli-agent")
        dl = FakeDispatchLayer()
        assert dl.dispatch(receiver_id="kilo-cli-agent", authority=valid).dispatch_decision == "AUTHORIZED"

        # Invalid transport contract
        invalid_transport = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            transport_contract_id="changed",
        )
        assert dl.dispatch(receiver_id="kilo-cli-agent", authority=invalid_transport).dispatch_decision == "REJECT"

        # Invalid model binding
        invalid_model = _build_valid_authority(
            receiver_id="kilo-cli-agent",
            model_binding_id="changed",
        )
        assert dl.dispatch(receiver_id="kilo-cli-agent", authority=invalid_model).dispatch_decision == "REJECT"


# --------------------------------------------------------------------------- #
# No execution
# --------------------------------------------------------------------------- #

class TestNoExecution:
    """Prove no real execution occurs."""

    def test_no_process_start(self, dispatch_layer):
        """No process is started during fake dispatch."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = dispatch_layer.dispatch(receiver_id="kilo-cli-agent", authority=authority)
        assert result.process_started is False

    def test_no_model_invocation(self, dispatch_layer):
        """No model is invoked during fake dispatch."""
        authority = _build_valid_authority(receiver_id="kilo-cli-agent")
        result = dispatch_layer.dispatch(receiver_id="kilo-cli-agent", authority=authority)
        assert result.model_invoked is False

    def test_no_fallback(self, dispatch_layer):
        """No fallback is attempted on rejection."""
        result = dispatch_layer.dispatch(receiver_id="unknown-receiver", authority=None)
        assert result.dispatch_decision == "REJECT"
        assert result.receiver_id is None

    def test_no_authority_creation_by_router(self):
        """Router does not create authority."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        # Router result has no authority artifact
        assert not hasattr(result, "authority")


# --------------------------------------------------------------------------- #
# Canonical material
# --------------------------------------------------------------------------- #

class TestCanonicalMaterial:
    """Prove canonical material reproducibility."""

    def test_canonical_json_reproducible(self):
        """Same canonical JSON across instances."""
        from tools.hermes_core.receiver_dispatch import get_authority_canonical_material
        m1 = get_authority_canonical_material()
        m2 = get_authority_canonical_material()
        assert m1 == m2

    def test_authority_contract_id_matches_material(self):
        """Authority contract ID is SHA-256 of canonical material."""
        from tools.hermes_core.hashing import sha256_payload
        material = get_authority_canonical_material()
        expected = sha256_payload(material)
        assert compute_ea4e7_authority_contract_id() == expected

    def test_router_contract_id_unchanged(self):
        """EA-4E.6 router contract ID is preserved."""
        # Router contract ID is derived from canonical material
        actual = compute_ea4e6_router_contract_id()
        # Verify it matches the computed value from canonical material
        from tools.hermes_core.hashing import sha256_payload
        router = get_default_router()
        expected = sha256_payload(router.get_canonical_material())
        assert actual == expected

    def test_qualified_receivers_frozen(self):
        """Qualified receiver set is exactly as expected."""
        receivers = set(QUALIFIED_RECEIVERS.keys())
        assert receivers == {"opencode-cli-agent", "kilo-cli-agent"}
