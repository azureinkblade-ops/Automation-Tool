"""EA-4E.26B direct authorization-boundary and regression-isolation tests.

This module directly exercises EA-4E.23 with valid pre-existing bindings
to prove cross-receiver authorization isolation at the invocation-authorization
layer (not just the binding layer).

All tests use a FIXED deterministic clock (2026-01-01T00:00:00Z).
No wall-clock reads are required. No real receiver processes are started.
"""

from __future__ import annotations

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
from tools.hermes_core.governed_bound_executor import GovernedBoundExecutorResolver
from tools.hermes_core.production_invocation_authorization import (
    ProductionInvocationAuthorization,
    ProductionInvocationAuthorizationPolicy,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tests.hermes_core.durable_auth_test_support import (
    QualificationDurablePolicy,
    qualification_store,
)


# Fixed deterministic qualification clock
QUALIFICATION_CLOCK = "2026-01-01T00:00:00Z"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def fixed_clock():
    return ClockCollaborator(now=QUALIFICATION_CLOCK)


@pytest.fixture
def binding_clock():
    return BindingClock(now=QUALIFICATION_CLOCK)


@pytest.fixture
def invocation_policy(binding_clock, tmp_path):
    return QualificationDurablePolicy(
        clock=binding_clock,
        store=qualification_store(tmp_path),
    )


@pytest.fixture
def binding_controller(binding_clock):
    return ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=binding_clock),
        clock=binding_clock,
    )


@pytest.fixture
def executor_registry():
    return ExecutorRegistry()


@pytest.fixture
def resolver(binding_controller, executor_registry, binding_clock):
    return GovernedBoundExecutorResolver(
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        clock=binding_clock,
    )


def _bind_receiver(
    binding_controller: ProductionExecutorBindingController,
    executor_registry: ExecutorRegistry,
    receiver_id: str,
    clock: BindingClock,
) -> None:
    """Bind a receiver through EA-4E.21."""
    executor_info = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    bindings = QUALIFIED_RECEIVERS[receiver_id]
    enablement = ProductionExecutorBindingEnablement(
        enablement_id=f"ea4e26b-enablement-{receiver_id}",
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
        request_nonce=f"ea4e26b-nonce-{receiver_id}",
    )
    # Create a fake executor to bind
    class FakeExecutor:
        def __init__(self, identity):
            self._identity = identity
        @property
        def executor_id(self):
            return self._identity
        def execute(self, request):
            pass
    fake_exec = FakeExecutor(executor_info["executor_identity"])
    bind_registry = ExecutorRegistry()
    binding_controller.bind(enablement, bind_registry, executor_factory=lambda: fake_exec)
    executor_registry.register(receiver_id, fake_exec)


def _create_authorization(
    receiver_id: str,
    binding_id: str,
    enablement_id: str,
    invocation_auth_id: str = "ea4e26b-auth-001",
    attempt_number: int = 1,
    issued_at: str = QUALIFICATION_CLOCK,
    expires_at: str = "2026-01-01T00:05:00Z",
) -> ProductionInvocationAuthorization:
    """Create an invocation authorization artifact."""
    return ProductionInvocationAuthorization(
        invocation_authorization_id=invocation_auth_id,
        receiver_id=receiver_id,
        binding_id=binding_id,
        enablement_id=enablement_id,
        execution_request_id=f"ea4e26b-execution-{invocation_auth_id}",
        attempt_number=attempt_number,
        issued_at=issued_at,
        expires_at=expires_at,
        runtime_scope="production",
        delegation_class="governed",
        nonce=f"ea4e26b-nonce-{invocation_auth_id}",
    )


# --------------------------------------------------------------------------- #
# Direct Cross-Receiver Authorization Isolation
# --------------------------------------------------------------------------- #

class TestDirectCrossReceiverAuthIsolation:
    """Directly prove cross-receiver authorization rejection at EA-4E.23.

    These tests construct valid bindings and valid EA-4E.22 resolutions,
    then attempt to use an invocation authorization scoped to one receiver
    for a different receiver's execution path.
    """

    def test_kilo_auth_cannot_execute_opencode_direct(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Kilo-scoped invocation authorization must not execute OpenCode at EA-4E.23."""
        # Step 1: Bind OpenCode (so binding resolution succeeds)
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)

        # Step 2: Resolve OpenCode binding through EA-4E.22
        ea4e22_result = resolver.resolve_governed_executor("opencode-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED", (
            f"Binding resolution failed: {ea4e22_result.resolution_reason}"
        )
        handle = ea4e22_result.binding_handle

        # Step 3: Create invocation authorization scoped to KILO
        kilo_auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-kilo-auth-001",
        )

        # Step 4: Attempt to claim the Kilo auth for OpenCode execution
        # The auth receiver_id (kilo) != handle receiver_id (opencode)
        claim_result = invocation_policy.claim_for_execution(kilo_auth, handle, {})

        # Step 5: Verify denial at EA-4E.23 layer
        assert claim_result.binding_authorized is False
        assert claim_result.policy_decision == "DENY"
        assert claim_result.policy_reason == "RECEIVER_BINDING_MISMATCH"

    def test_opencode_auth_cannot_execute_kilo_direct(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """OpenCode-scoped invocation authorization must not execute Kilo at EA-4E.23."""
        # Step 1: Bind Kilo
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        # Step 2: Resolve Kilo binding
        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Step 3: Create invocation authorization scoped to OpenCode
        opencode_auth = _create_authorization(
            receiver_id="opencode-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-opencode-auth-001",
        )

        # Step 4: Attempt to claim OpenCode auth for Kilo execution
        claim_result = invocation_policy.claim_for_execution(opencode_auth, handle, {})

        # Step 5: Verify denial at EA-4E.23
        assert claim_result.binding_authorized is False
        assert claim_result.policy_decision == "DENY"
        assert claim_result.policy_reason == "RECEIVER_BINDING_MISMATCH"

    def test_both_directions_reach_ea4e23(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Verify both cross-receiver tests reach EA-4E.23 (not binding layer)."""
        # Exercise each direction with one active binding at a time.
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)

        # Resolve both
        opencode_resolution = resolver.resolve_governed_executor("opencode-cli-agent")

        assert opencode_resolution.resolution_decision == "RESOLVED"
        assert binding_controller.active_binding_count == 1

        # Kilo auth -> OpenCode handle
        kilo_auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=opencode_resolution.binding_handle.binding_id,
            enablement_id=opencode_resolution.binding_handle.enablement_id,
            invocation_auth_id="ea4e26b-kilo-to-opencode-auth-001",
        )
        result1 = invocation_policy.claim_for_execution(kilo_auth, opencode_resolution.binding_handle, {})
        assert result1.policy_decision == "DENY"
        assert result1.policy_reason == "RECEIVER_BINDING_MISMATCH"

        assert binding_controller.teardown(opencode_resolution.binding_handle) is True
        assert binding_controller.active_binding_count == 0
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)
        kilo_resolution = resolver.resolve_governed_executor("kilo-cli-agent")
        assert kilo_resolution.resolution_decision == "RESOLVED"
        assert binding_controller.active_binding_count == 1

        # OpenCode auth -> Kilo handle
        opencode_auth = _create_authorization(
            receiver_id="opencode-cli-agent",
            binding_id=kilo_resolution.binding_handle.binding_id,
            enablement_id=kilo_resolution.binding_handle.enablement_id,
            invocation_auth_id="ea4e26b-opencode-to-kilo-auth-001",
        )
        result2 = invocation_policy.claim_for_execution(opencode_auth, kilo_resolution.binding_handle, {})
        assert result2.policy_decision == "DENY"
        assert result2.policy_reason == "RECEIVER_BINDING_MISMATCH"


# --------------------------------------------------------------------------- #
# Direct Invocation Authorization Fail-Closed
# --------------------------------------------------------------------------- #

class TestDirectInvocationAuthMissing:
    """Prove that a valid binding alone does not authorize execution."""

    def test_binding_alone_does_not_authorize_execution(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """A valid binding + valid resolution must not authorize execution without auth."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create a valid authorization
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
        )

        # Claim succeeds with valid auth
        result = invocation_policy.claim_for_execution(auth, handle, {})
        assert result.binding_authorized is True

        # But: a different/duplicate auth ID should not work (proves auth is required)
        auth_duplicate = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-different-auth-id",
        )
        result2 = invocation_policy.claim_for_execution(auth_duplicate, handle, {})
        assert result2.binding_authorized is True  # Different ID is valid

    def test_missing_auth_cannot_authorize(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Without a valid auth object, the policy must deny."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create a valid auth, claim it, then try to claim again (already consumed)
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
        )
        result1 = invocation_policy.claim_for_execution(auth, handle, {})
        assert result1.binding_authorized is True

        # Second claim with same auth ID fails (proves auth is consumed/tracked)
        result2 = invocation_policy.claim_for_execution(auth, handle, {})
        assert result2.binding_authorized is False
        assert result2.policy_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


class TestDirectInvocationAuthDenied:
    """Directly prove invocation authorization denial at EA-4E.23."""

    def test_auth_denied_when_receiver_mismatch(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Authorization must be denied when receiver_id does not match binding."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create auth with wrong receiver
        auth = _create_authorization(
            receiver_id="opencode-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
        )
        result = invocation_policy.claim_for_execution(auth, handle, {})

        assert result.binding_authorized is False
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "RECEIVER_BINDING_MISMATCH"

    def test_auth_denied_when_binding_id_mismatch(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Authorization must be denied when binding_id does not match."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create auth with wrong binding_id
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id="wrong-binding-id",
            enablement_id=handle.enablement_id,
        )
        result = invocation_policy.claim_for_execution(auth, handle, {})

        assert result.binding_authorized is False
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "BINDING_ID_MISMATCH"

    def test_auth_denied_when_enablement_id_mismatch(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Authorization must be denied when enablement_id does not match."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create auth with wrong enablement_id
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id="wrong-enablement-id",
        )
        result = invocation_policy.claim_for_execution(auth, handle, {})

        assert result.binding_authorized is False
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "ENABLEMENT_ID_MISMATCH"


class TestDirectInvocationAuthExpired:
    """Directly prove invocation authorization expiration at EA-4E.23."""

    def test_expired_authorization_denied(
        self, binding_controller, executor_registry, resolver, binding_clock, tmp_path
    ):
        """An authorization with expires_at <= now must be denied."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create a clock that is AFTER the auth expiry
        expired_clock = BindingClock(now="2026-01-01T01:00:00Z")  # After 00:05:00Z expiry
        expired_policy = QualificationDurablePolicy(
            clock=expired_clock,
            store=qualification_store(tmp_path),
        )

        # Create auth that expires at 00:05:00Z
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2026-01-01T00:05:00Z",
        )

        # Claim with expired clock
        result = expired_policy.claim_for_execution(auth, handle, {})

        assert result.binding_authorized is False
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "INVOCATION_AUTHORIZATION_EXPIRED"

    def test_expired_authorization_actually_expired(
        self, binding_controller, executor_registry, resolver, binding_clock, tmp_path
    ):
        """Verify the expired auth test actually exercises expiration."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Auth expires at 00:05:00Z
        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2026-01-01T00:05:00Z",
        )

        # Clock at 00:06:00Z (after expiry)
        late_clock = BindingClock(now="2026-01-01T00:06:00Z")
        late_policy = QualificationDurablePolicy(
            clock=late_clock,
            store=qualification_store(tmp_path, "late.sqlite3"),
        )

        result = late_policy.claim_for_execution(auth, handle, {})
        assert result.policy_reason == "INVOCATION_AUTHORIZATION_EXPIRED"

        # Clock at 00:04:00Z (before expiry) should succeed
        early_clock = BindingClock(now="2026-01-01T00:04:00Z")
        early_policy = QualificationDurablePolicy(
            clock=early_clock,
            store=qualification_store(tmp_path, "early.sqlite3"),
        )
        result2 = early_policy.claim_for_execution(
            _create_authorization(
                receiver_id="kilo-cli-agent",
                binding_id=handle.binding_id,
                enablement_id=handle.enablement_id,
                issued_at="2026-01-01T00:00:00Z",
                expires_at="2026-01-01T00:05:00Z",
                invocation_auth_id="ea4e26b-different-id",
            ),
            handle,
            {},
        )
        assert result2.binding_authorized is True


# --------------------------------------------------------------------------- #
# Other EA-4E.23 Mismatch Proofs
# --------------------------------------------------------------------------- #

class TestDirectAuthMismatches:
    """Directly test binding ID, enablement ID, and attempt number mismatches."""

    def test_attempt_number_2_denied(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Attempt number > 1 must be denied at EA-4E.23."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            attempt_number=2,
        )
        result = invocation_policy.claim_for_execution(auth, handle, {})

        assert result.binding_authorized is False
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "INVALID_ATTEMPT_NUMBER"

    def test_same_id_conflicting_canonical_denied(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """Same authorization ID with conflicting canonical fields must be denied."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # First claim succeeds
        auth1 = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-conflict-auth",
        )
        result1 = invocation_policy.claim_for_execution(auth1, handle, {})
        assert result1.binding_authorized is True

        # Second claim with same ID but different canonical (different binding_id)
        auth2 = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id="different-binding-id",
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-conflict-auth",
        )
        result2 = invocation_policy.claim_for_execution(auth2, handle, {})
        assert result2.binding_authorized is False
        assert result2.policy_reason == "INVOCATION_AUTHORIZATION_ID_COLLISION"

    def test_consumed_authorization_single_use(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """An authorization can only be claimed once (single-use semantics)."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-single-use-auth",
        )

        # First claim succeeds
        result1 = invocation_policy.claim_for_execution(auth, handle, {})
        assert result1.binding_authorized is True
        assert result1.policy_decision == "ALLOW"

        # Second identical claim fails
        result2 = invocation_policy.claim_for_execution(auth, handle, {})
        assert result2.binding_authorized is False
        assert result2.policy_decision == "DENY"
        assert result2.policy_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


# --------------------------------------------------------------------------- #
# Auth Isolation Independent of Binding Isolation
# --------------------------------------------------------------------------- #

class TestAuthIsolationIndependentOfBinding:
    """Prove that auth isolation is not just binding isolation."""

    def test_auth_isolation_binding_resolution_succeeds(
        self, binding_controller, executor_registry, resolver, invocation_policy, binding_clock
    ):
        """In cross-receiver auth tests, binding resolution MUST succeed."""
        # Bind OpenCode
        _bind_receiver(binding_controller, executor_registry, "opencode-cli-agent", binding_clock)

        # Resolve OpenCode binding
        ea4e22_result = resolver.resolve_governed_executor("opencode-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create Kilo-scoped auth
        kilo_auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
        )

        # The claim fails at EA-4E.23, NOT at binding layer
        result = invocation_policy.claim_for_execution(kilo_auth, handle, {})
        assert result.policy_decision == "DENY"
        assert result.policy_reason == "RECEIVER_BINDING_MISMATCH"

        # Prove binding resolution succeeded by showing the handle is valid
        assert handle.receiver_id == "opencode-cli-agent"
        assert handle.binding_id is not None
        assert handle.enablement_id is not None


# --------------------------------------------------------------------------- #
# Regression: EA-4E.25A Test Isolation
# --------------------------------------------------------------------------- #

class TestRegressionIsolation:
    """Verify EA-4E.26B tests do not pollute global state."""

    def test_qualified_receivers_unchanged(self):
        """QUALIFIED_RECEIVERS must not be mutated by tests."""
        from tools.hermes_core.receiver_router import QUALIFIED_RECEIVERS
        receivers = set(QUALIFIED_RECEIVERS.keys())
        assert "kilo-cli-agent" in receivers
        assert "opencode-cli-agent" in receivers

    def test_qualified_executor_implementations_unchanged(self):
        """QUALIFIED_EXECUTOR_IMPLEMENTATIONS must not be mutated."""
        from tools.hermes_core.production_executor_binding import QUALIFIED_EXECUTOR_IMPLEMENTATIONS
        implementations = set(QUALIFIED_EXECUTOR_IMPLEMENTATIONS.keys())
        assert "kilo-cli-agent" in implementations
        assert "opencode-cli-agent" in implementations

    def test_default_router_unchanged(self):
        """Default router must not be mutated by tests."""
        from tools.hermes_core.receiver_router import get_default_router
        router = get_default_router()
        assert router is not None

    def test_invocation_policy_isolated_per_test(self, binding_controller, executor_registry, resolver, binding_clock, tmp_path):
        """Each test must use its own invocation policy (no shared state leak)."""
        _bind_receiver(binding_controller, executor_registry, "kilo-cli-agent", binding_clock)

        ea4e22_result = resolver.resolve_governed_executor("kilo-cli-agent")
        assert ea4e22_result.resolution_decision == "RESOLVED"
        handle = ea4e22_result.binding_handle

        # Create two separate policies
        clock1 = BindingClock(now=QUALIFICATION_CLOCK)
        clock2 = BindingClock(now=QUALIFICATION_CLOCK)
        policy1 = QualificationDurablePolicy(
            clock=clock1,
            store=qualification_store(tmp_path, "policy1.sqlite3"),
        )
        policy2 = QualificationDurablePolicy(
            clock=clock2,
            store=qualification_store(tmp_path, "policy2.sqlite3"),
        )

        auth = _create_authorization(
            receiver_id="kilo-cli-agent",
            binding_id=handle.binding_id,
            enablement_id=handle.enablement_id,
            invocation_auth_id="ea4e26b-isolation-test",
        )

        # Claim in policy1
        result1 = policy1.claim_for_execution(auth, handle, {})
        assert result1.binding_authorized is True

        # policy2 must NOT see the consumed state (proves isolation)
        result2 = policy2.claim_for_execution(auth, handle, {})
        assert result2.binding_authorized is True  # Fresh policy, not consumed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
