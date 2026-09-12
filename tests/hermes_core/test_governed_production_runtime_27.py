"""EA-4E.27 external invocation-authorization boundary qualification."""

from dataclasses import replace
import inspect

import pytest

from tools.hermes_core.governed_production_runtime import GovernedProductionRuntime
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    ProductionExecutorBindingController,
    ProductionExecutorBindingPolicy,
)
from tools.hermes_core.production_issuance import ClockCollaborator
from tests.hermes_core.test_governed_production_runtime import (
    FakeFailingKiloExecutor,
    QUALIFICATION_CLOCK,
    _bind_receiver,
    _make_authorized_request,
    _make_request,
)
from tests.hermes_core.durable_auth_test_support import (
    QualificationDurablePolicy,
    qualification_store,
)


@pytest.fixture
def binding_clock():
    return BindingClock(now=QUALIFICATION_CLOCK)


@pytest.fixture
def executor_registry():
    return ExecutorRegistry()


@pytest.fixture
def binding_controller(binding_clock):
    return ProductionExecutorBindingController(
        policy=ProductionExecutorBindingPolicy(clock=binding_clock),
        clock=binding_clock,
    )


def _durable_runtime(binding_controller, executor_registry, tmp_path, name):
    clock = ClockCollaborator(now=QUALIFICATION_CLOCK)
    return GovernedProductionRuntime(
        clock=clock,
        binding_controller=binding_controller,
        executor_registry=executor_registry,
        invocation_authorization_policy=QualificationDurablePolicy(
            clock=clock,
            store=qualification_store(tmp_path, name),
        ),
    )


@pytest.fixture
def runtime(binding_controller, executor_registry, tmp_path):
    return _durable_runtime(
        binding_controller, executor_registry, tmp_path, "runtime27.sqlite3"
    )


def _bind(binding_controller, executor_registry, binding_clock, receiver_id="kilo-cli-agent"):
    _bind_receiver(binding_controller, executor_registry, receiver_id, binding_clock)


def _execute_with_auth(runtime, binding_controller, **auth_changes):
    request = _make_authorized_request(binding_controller)
    if auth_changes:
        request = replace(
            request,
            invocation_authorization=replace(
                request.invocation_authorization,
                **auth_changes,
            ),
        )
    return runtime.execute(request)


class TestExternalAuthorizationBoundary:
    def test_01_missing_auth_denies_after_binding_resolution(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock)
        result = runtime.execute(_make_request())
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_decision == "DENY"
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_REQUIRED"
        assert result.executor_called is False

    def test_02_valid_external_kilo_auth_executes_once(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller)
        assert result.invocation_claim_decision == "ALLOW"
        assert result.execution_output == "EA4E26_KILO_FAKE_GOVERNED_RUNTIME_OK"
        assert result.kilo_executor_calls == 1

    def test_03_valid_external_opencode_auth_executes_once(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock, "opencode-cli-agent")
        request = _make_authorized_request(
            binding_controller, receiver_id="opencode-cli-agent"
        )
        result = runtime.execute(request)
        assert result.invocation_claim_decision == "ALLOW"
        assert result.execution_output == "EA4E26_OPENCODE_FAKE_GOVERNED_RUNTIME_OK"
        assert result.opencode_executor_calls == 1

    def test_04_kilo_auth_cannot_execute_opencode_at_ea4e23(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock, "opencode-cli-agent")
        request = _make_authorized_request(
            binding_controller,
            receiver_id="opencode-cli-agent",
            authorization_receiver_id="kilo-cli-agent",
        )
        result = runtime.execute(request)
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_reason == "RECEIVER_BINDING_MISMATCH"
        assert result.executor_called is False

    def test_05_opencode_auth_cannot_execute_kilo_at_ea4e23(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(
            runtime, binding_controller, receiver_id="opencode-cli-agent"
        )
        assert result.ea4e22_resolution_decision == "RESOLVED"
        assert result.invocation_claim_reason == "RECEIVER_BINDING_MISMATCH"
        assert result.executor_called is False

    def test_06_expired_auth_denies_at_ea4e23(
        self, runtime, binding_controller, executor_registry, binding_clock
    ):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(
            runtime, binding_controller, expires_at=QUALIFICATION_CLOCK
        )
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_EXPIRED"
        assert result.executor_called is False

    def test_07_receiver_mismatch_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, receiver_id="opencode-cli-agent")
        assert result.invocation_claim_reason == "RECEIVER_BINDING_MISMATCH"

    def test_08_binding_id_mismatch_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, binding_id="wrong-binding")
        assert result.invocation_claim_reason == "BINDING_ID_MISMATCH"

    def test_09_enablement_id_mismatch_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, enablement_id="wrong-enablement")
        assert result.invocation_claim_reason == "ENABLEMENT_ID_MISMATCH"

    def test_10_request_identity_mismatch_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, execution_request_id="wrong-request")
        assert result.invocation_claim_reason == "REQUEST_IDENTITY_MISMATCH"

    def test_11_attempt_two_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, attempt_number=2)
        assert result.invocation_claim_reason == "INVALID_ATTEMPT_NUMBER"

    def test_12_consumed_auth_denies_second_claim(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        request = _make_authorized_request(binding_controller)
        assert runtime.execute(request).invocation_claim_decision == "ALLOW"
        second = runtime.execute(request)
        assert second.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"
        assert second.executor_called is False

    def test_13_same_id_conflicting_canonical_denies(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        request = _make_authorized_request(binding_controller)
        assert runtime.execute(request).invocation_claim_decision == "ALLOW"
        collision = replace(
            request,
            invocation_authorization=replace(
                request.invocation_authorization,
                nonce="conflicting-canonical-nonce",
            ),
        )
        result = runtime.execute(collision)
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ID_COLLISION"
        assert result.executor_called is False


class TestNoAutomaticAuthorization:
    def test_14_runtime_source_does_not_construct_authorization(self):
        source = inspect.getsource(GovernedProductionRuntime.execute)
        assert "ProductionInvocationAuthorization(" not in source

    def test_15_missing_auth_does_not_auto_create(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = runtime.execute(_make_request())
        assert result.live_invocation_authorizations_issued == 0
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_REQUIRED"

    def test_16_invalid_auth_does_not_trigger_replacement(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, binding_id="invalid")
        assert result.live_invocation_authorizations_issued == 0
        assert result.invocation_claim_reason == "BINDING_ID_MISMATCH"

    def test_17_expired_auth_does_not_trigger_refresh(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        result = _execute_with_auth(runtime, binding_controller, expires_at=QUALIFICATION_CLOCK)
        assert result.live_invocation_authorizations_issued == 0
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_EXPIRED"

    def test_18_consumed_auth_does_not_trigger_replacement(self, runtime, binding_controller, executor_registry, binding_clock):
        _bind(binding_controller, executor_registry, binding_clock)
        request = _make_authorized_request(binding_controller)
        runtime.execute(request)
        result = runtime.execute(request)
        assert result.live_invocation_authorizations_issued == 0
        assert result.invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"


class TestPreservedRuntimeControls:
    def test_19_executor_failure_has_no_fallback(self, binding_controller, executor_registry, binding_clock, tmp_path):
        _bind(binding_controller, executor_registry, binding_clock)
        executor_registry.register("kilo-cli-agent", FakeFailingKiloExecutor())
        runtime = _durable_runtime(
            binding_controller, executor_registry, tmp_path, "case19.sqlite3"
        )
        result = runtime.execute(_make_authorized_request(binding_controller))
        assert result.execution_status == "FAILURE"
        assert result.fallback_attempts == 0
        assert result.opencode_executor_calls == 0

    def test_20_executor_failure_has_no_retry(self, binding_controller, executor_registry, binding_clock, tmp_path):
        _bind(binding_controller, executor_registry, binding_clock)
        executor_registry.register("kilo-cli-agent", FakeFailingKiloExecutor())
        runtime = _durable_runtime(
            binding_controller, executor_registry, tmp_path, "case20.sqlite3"
        )
        result = runtime.execute(_make_authorized_request(binding_controller))
        assert result.automatic_retry_attempts == 0

    def test_21_runtime_does_not_auto_bind(self, runtime):
        result = runtime.execute(_make_request())
        assert result.binding_reason == "NO_ACTIVE_EXECUTOR_BINDING"
        assert result.automatic_executor_binding_enabled is False

    def test_22_runtime_has_no_default_receiver(self, runtime):
        result = runtime.execute(_make_request(receiver_id=""))
        assert result.route_decision == "REJECT"
        assert result.default_receiver == "NONE"

    def test_23_runtime_default_auto_auth_is_off(self, runtime):
        result = runtime.execute(_make_request())
        assert result.automatic_invocation_authorization_enabled is False

    def test_24_external_auth_is_consumed_before_executor_failure(
        self, binding_controller, executor_registry, binding_clock, tmp_path
    ):
        _bind(binding_controller, executor_registry, binding_clock)
        executor_registry.register("kilo-cli-agent", FakeFailingKiloExecutor())
        runtime = _durable_runtime(
            binding_controller, executor_registry, tmp_path, "case24.sqlite3"
        )
        request = _make_authorized_request(binding_controller)
        assert runtime.execute(request).execution_status == "FAILURE"
        assert runtime.execute(request).invocation_claim_reason == "INVOCATION_AUTHORIZATION_ALREADY_CONSUMED"
