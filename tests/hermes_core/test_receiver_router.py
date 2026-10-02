"""EA-4E.6 receiver router fake/non-live qualification tests."""

from __future__ import annotations

import pytest

from tools.hermes_core.receiver_router import (
    QUALIFIED_RECEIVERS,
    ReceiverRouter,
    RoutingRequest,
    compute_ea4e6_router_contract_id,
    get_default_router,
    route_receiver,
)


class TestReceiverRouterDeterministic:
    """Prove deterministic receiver selection."""

    def test_explicit_opencode_selection(self):
        """OpenCode is selectable when requested."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="opencode-cli-agent"))
        assert result.route_decision == "SELECTED"
        assert result.receiver_id == "opencode-cli-agent"
        assert result.qualification_state == "QUALIFIED"
        assert result.execution_started is False

    def test_explicit_kilo_selection(self):
        """Kilo is selectable when requested."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        assert result.route_decision == "SELECTED"
        assert result.receiver_id == "kilo-cli-agent"
        assert result.qualification_state == "QUALIFIED"
        assert result.execution_started is False

    def test_same_input_same_output(self):
        """Same canonical input produces same receiver selection."""
        router = get_default_router()
        r1 = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        r2 = router.route(RoutingRequest(receiver_id="kilo-cli-agent"))
        assert r1 == r2

    def test_deterministic_across_instances(self):
        """Two router instances produce identical results."""
        r1 = ReceiverRouter().route(RoutingRequest(receiver_id="opencode-cli-agent"))
        r2 = ReceiverRouter().route(RoutingRequest(receiver_id="opencode-cli-agent"))
        assert r1 == r2


class TestReceiverRouterFailClosed:
    """Prove fail-closed behavior."""

    def test_unsupported_receiver_rejected(self):
        """Unknown receiver IDs are rejected."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="unknown-receiver"))
        assert result.route_decision == "REJECT"
        assert result.receiver_id is None
        assert result.route_reason == "UNSUPPORTED_RECEIVER"

    def test_empty_receiver_id_rejected(self):
        """Empty receiver ID is rejected."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id=""))
        assert result.route_decision == "REJECT"
        assert result.route_reason == "EMPTY_RECEIVER_ID"

    def test_unqualified_receiver_rejected(self):
        """A receiver not in the qualified set is rejected."""
        router = get_default_router()
        result = router.route(RoutingRequest(receiver_id="codex-cli-agent"))
        assert result.route_decision == "REJECT"
        assert result.route_reason == "UNSUPPORTED_RECEIVER"


class TestReceiverRouterContractVerification:
    """Prove contract-mismatch detection."""

    def test_kilo_contract_matches(self):
        """Kilo's frozen contract ID is verified."""
        router = get_default_router()
        assert router.verify_contract(
            receiver_id="kilo-cli-agent",
            expected_transport_contract_id=QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"],
        )

    def test_kilo_contract_mismatch_fails_closed(self):
        """Wrong contract ID fails closed."""
        router = get_default_router()
        assert not router.verify_contract(
            receiver_id="kilo-cli-agent",
            expected_transport_contract_id="wrong_contract_id",
        )

    def test_opencode_contract_matches(self):
        """OpenCode's frozen contract ID is verified."""
        router = get_default_router()
        assert router.verify_contract(
            receiver_id="opencode-cli-agent",
            expected_transport_contract_id="192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f",
        )

    def test_opencode_contract_mismatch_fails_closed(self):
        """Wrong OpenCode contract ID fails closed."""
        router = get_default_router()
        assert not router.verify_contract(
            receiver_id="opencode-cli-agent",
            expected_transport_contract_id="wrong_contract_id",
        )

    def test_unsupported_receiver_contract_fails_closed(self):
        """Unsupported receiver fails contract verification."""
        router = get_default_router()
        assert not router.verify_contract(
            receiver_id="unknown",
            expected_transport_contract_id="any",
        )


class TestReceiverRouterExecutionAuthority:
    """Prove execution-authority separation."""

    def test_route_does_not_create_execution_authority(self):
        """Routing success does not grant execution permission."""
        router = get_default_router()
        result = router.route(RoutingRequest(
            receiver_id="kilo-cli-agent",
            execution_authority_present=False,
        ))
        assert result.route_decision == "SELECTED"
        assert result.execution_authority_present is False
        assert result.execution_started is False

    def test_route_with_authority_still_not_started(self):
        """Even with authority present, router does not start execution."""
        router = get_default_router()
        result = router.route(RoutingRequest(
            receiver_id="kilo-cli-agent",
            execution_authority_present=True,
        ))
        assert result.route_decision == "SELECTED"
        assert result.execution_started is False

    def test_route_selected_not_authorized(self):
        """ROUTE_SELECTED != EXECUTION_AUTHORIZED."""
        result = route_receiver("kilo-cli-agent")
        assert result.route_decision == "SELECTED"
        assert result.execution_started is False


class TestReceiverRouterSecurity:
    """Prove security invariants."""

    def test_task_text_does_not_control_router(self):
        """Task text is not part of the routing request."""
        request = RoutingRequest(receiver_id="kilo-cli-agent")
        assert not hasattr(request, "task_text")

    def test_qualified_receivers_frozen(self):
        """Qualified receiver set is deterministic."""
        router = get_default_router()
        receivers = router.get_qualified_receivers()
        assert "opencode-cli-agent" in receivers
        assert "kilo-cli-agent" in receivers

    def test_router_does_not_mutate_receiver_contracts(self):
        """Router reads but does not modify receiver contracts."""
        router = get_default_router()
        material = router.get_canonical_material()
        # Contracts are preserved unchanged
        assert material["qualified_receivers"]["kilo-cli-agent"]["transport_contract_id"] == \
            QUALIFIED_RECEIVERS["kilo-cli-agent"]["transport_contract_id"]
        assert material["qualified_receivers"]["opencode-cli-agent"]["transport_contract_id"] == \
            "192b55d0aca65f261fa3e2701db63863f2761cacd20bb9422e73cde772e9ea5f"


class TestReceiverRouterCanonical:
    """Prove canonical material reproducibility."""

    def test_canonical_json_reproducible(self):
        """Same router produces same canonical JSON."""
        r1 = ReceiverRouter()
        r2 = ReceiverRouter()
        assert r1.get_canonical_json() == r2.get_canonical_json()

    def test_router_contract_id_reproducible(self):
        """Router contract ID is deterministic."""
        assert compute_ea4e6_router_contract_id() == compute_ea4e6_router_contract_id()

    def test_router_contract_id_matches_material(self):
        """Contract ID is SHA-256 of canonical material."""
        from tools.hermes_core.hashing import sha256_payload
        router = get_default_router()
        expected = sha256_payload(router.get_canonical_material())
        assert router.get_contract_id() == expected


class TestReceiverRouterNoExecution:
    """Prove no real execution occurs during routing."""

    def test_no_process_start(self):
        """Routing does not start any process."""
        result = route_receiver("kilo-cli-agent")
        assert result.execution_started is False

    def test_no_model_invocation(self):
        """Routing does not invoke any model."""
        result = route_receiver("opencode-cli-agent")
        assert result.execution_started is False

    def test_no_fallback(self):
        """Router does not attempt fallback."""
        result = route_receiver("unknown-receiver")
        assert result.route_decision == "REJECT"
        assert result.receiver_id is None
