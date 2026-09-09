"""EA-4E.53 in-process request lifecycle qualification. Fake only."""

from __future__ import annotations

from dataclasses import dataclass
import inspect

import pytest

import app
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import (
    _bind,
    _configure,
    _payload as _governed_payload,
    _provision_issue,
    _ready,
)
from tools.hermes_core.production_app_binding import ProductionAppBindingProvisioner
from tools.hermes_core.production_app_host import ProductionAppHostResult
from tools.hermes_core.production_app_lifecycle import (
    ProductionAppRequestLifecycleOwner,
)
from tools.hermes_core.production_executor_binding import (
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)


@dataclass(frozen=True)
class FakeBinding:
    receiver_id: str = "kilo-cli-agent"


class FakeBindingController:
    def __init__(self, binding=None, *, teardown_result=True, teardown_error=None):
        self.binding = binding
        self.teardown_result = teardown_result
        self.teardown_error = teardown_error
        self.lookups = []
        self.teardown_calls = []

    def get_binding_for_receiver(self, receiver_id):
        self.lookups.append(receiver_id)
        if self.binding is not None and self.binding.receiver_id == receiver_id:
            return self.binding
        return None

    def teardown(self, binding):
        self.teardown_calls.append(binding)
        if self.teardown_error is not None:
            raise self.teardown_error
        if self.teardown_result:
            self.binding = None
        return self.teardown_result


class FakeGovernedAction:
    def __init__(self, *, result=None, error=None):
        self.result = result or ProductionAppHostResult(
            decision="ALLOW",
            reason="FAKE_SUCCESS",
            receiver_id="kilo-cli-agent",
        )
        self.error = error
        self.calls = 0

    def submit(self, payload):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class RaisingFakeExecutor:
    def __init__(self, receiver_id, error):
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id][
            "executor_identity"
        ]
        self.error = error
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        raise self.error


def _payload(receiver_id="kilo-cli-agent"):
    return {
        "request_id": "ea4e53-fake",
        "receiver_id": receiver_id,
        "task_payload": "EA4E53_FAKE",
    }


def _owner(*, result=None, action_error=None, teardown_result=True, teardown_error=None):
    binding = FakeBinding()
    controller = FakeBindingController(
        binding,
        teardown_result=teardown_result,
        teardown_error=teardown_error,
    )
    action = FakeGovernedAction(result=result, error=action_error)
    return ProductionAppRequestLifecycleOwner(action, controller), action, controller


def test_success_tears_down_exact_binding_once():
    owner, action, controller = _owner()
    result = owner.submit(_payload())
    assert result.decision == "ALLOW"
    assert action.calls == 1
    assert controller.teardown_calls == [FakeBinding()]
    assert controller.binding is None


def test_governed_denial_remains_denial_and_tears_down_once():
    denied = ProductionAppHostResult(decision="DENY", reason="FAKE_DENIAL")
    owner, action, controller = _owner(result=denied)
    result = owner.submit(_payload())
    assert (result.decision, result.reason) == ("DENY", "FAKE_DENIAL")
    assert action.calls == 1
    assert len(controller.teardown_calls) == 1


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RuntimeError("executor"), "GOVERNED_ACTION_EXCEPTION:RuntimeError"),
        (TimeoutError("timeout"), "GOVERNED_ACTION_EXCEPTION:TimeoutError"),
        (ValueError("application"), "GOVERNED_ACTION_EXCEPTION:ValueError"),
    ],
)
def test_action_failures_teardown_once_without_retry(error, reason):
    owner, action, controller = _owner(action_error=error)
    result = owner.submit(_payload())
    assert (result.decision, result.reason) == ("DENY", reason)
    assert action.calls == 1
    assert len(controller.teardown_calls) == 1


def test_missing_binding_fails_closed_without_action_or_teardown():
    controller = FakeBindingController(binding=None)
    action = FakeGovernedAction()
    owner = ProductionAppRequestLifecycleOwner(action, controller)
    result = owner.submit(_payload())
    assert (result.decision, result.reason) == ("DENY", "MISSING_EXPLICIT_BINDING")
    assert action.calls == 0
    assert controller.teardown_calls == []


def test_explicit_binding_provisioning_denial_has_no_action_or_teardown():
    provisioning = ProductionAppBindingProvisioner(None, None).bind(None)
    assert provisioning.binding_decision == "DENY"

    controller = FakeBindingController(binding=None)
    action = FakeGovernedAction()
    result = ProductionAppRequestLifecycleOwner(action, controller).submit(_payload())
    assert result.decision == "DENY"
    assert action.calls == 0
    assert controller.teardown_calls == []


@pytest.mark.parametrize(
    ("teardown_result", "teardown_error", "reason"),
    [
        (False, None, "BINDING_TEARDOWN_NOT_CONFIRMED"),
        (True, RuntimeError("cleanup"), "BINDING_TEARDOWN_EXCEPTION:RuntimeError"),
    ],
)
def test_teardown_failure_is_surfaced_without_second_execution_or_binding(
    teardown_result, teardown_error, reason
):
    owner, action, controller = _owner(
        teardown_result=teardown_result,
        teardown_error=teardown_error,
    )
    result = owner.submit(_payload())
    assert (result.decision, result.reason) == ("DENY", reason)
    assert action.calls == 1
    assert len(controller.lookups) == 1
    assert len(controller.teardown_calls) == 1


def test_teardown_failure_overrides_action_failure_without_retry():
    owner, action, controller = _owner(
        action_error=TimeoutError("timeout"),
        teardown_result=False,
    )
    result = owner.submit(_payload())
    assert result.reason == "BINDING_TEARDOWN_NOT_CONFIRMED"
    assert action.calls == 1
    assert len(controller.teardown_calls) == 1


def test_response_translation_occurs_after_teardown(monkeypatch):
    class TranslationFailureResult:
        def to_public_dict(self):
            raise RuntimeError("translation")

    owner, _, controller = _owner(result=TranslationFailureResult())
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", owner)
    with pytest.raises(RuntimeError, match="translation"):
        app.submit_governed_production_action(_payload())
    assert len(controller.teardown_calls) == 1
    assert controller.binding is None


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_actual_app_host_fake_receiver_path_tears_down(tmp_path, receiver_id):
    components, fake, payload = _ready(tmp_path, receiver_id, f"ea4e53-{receiver_id}")
    assert components.composition.binding_controller.active_binding_count == 1
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert result["receiverId"] == receiver_id
    assert fake.calls == 1
    assert components.composition.binding_controller.active_binding_count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authorization_issue_request", None),
        ("execution_authority", None),
        ("activation", None),
    ],
)
def test_actual_governance_denials_after_binding_still_teardown(tmp_path, field, value):
    components, fake, payload = _ready(
        tmp_path,
        "kilo-cli-agent",
        f"ea4e53-denial-{field}",
    )
    payload[field] = value
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0
    assert components.composition.binding_controller.active_binding_count == 0


@pytest.mark.parametrize("error", [RuntimeError("executor"), TimeoutError("timeout")])
def test_actual_fake_executor_failures_still_teardown(tmp_path, error):
    receiver_id = "kilo-cli-agent"
    request_id = f"ea4e53-executor-{type(error).__name__}"
    components, _, clock = _configure(tmp_path, receiver_id)
    executor = RaisingFakeExecutor(receiver_id, error)
    components.composition.executor_registry.register(receiver_id, executor)
    binding = _bind(components, receiver_id)
    authority, activation = external_authority_and_activation(
        receiver_id,
        request_id,
        clock=clock,
    )
    provisioned = _provision_issue(
        receiver_id,
        request_id,
        authority,
        binding.handle,
    )
    payload = _governed_payload(
        receiver_id,
        request_id,
        authority,
        activation,
        provisioned.issue_request,
    )

    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert executor.calls == 1
    assert components.composition.binding_controller.active_binding_count == 0


def test_grok_is_denied_without_action_or_teardown():
    controller = FakeBindingController(binding=None)
    action = FakeGovernedAction()
    owner = ProductionAppRequestLifecycleOwner(action, controller)
    result = owner.submit(_payload("grok"))
    assert result.decision == "DENY"
    assert action.calls == 0
    assert controller.teardown_calls == []


def test_missing_receiver_cannot_be_inferred_from_task_text():
    controller = FakeBindingController(binding=None)
    action = FakeGovernedAction(
        result=ProductionAppHostResult(decision="DENY", reason="MISSING_RECEIVER")
    )
    owner = ProductionAppRequestLifecycleOwner(action, controller)
    result = owner.submit({"task_payload": "use kilo-cli-agent"})
    assert result.reason == "MISSING_RECEIVER"
    assert controller.lookups == []
    assert controller.teardown_calls == []


def test_missing_dependencies_fail_closed():
    result = ProductionAppRequestLifecycleOwner(None, None).submit(_payload())
    assert (result.decision, result.reason) == (
        "DENY",
        "MISSING_REQUEST_LIFECYCLE_DEPENDENCY",
    )


def test_owner_has_no_binding_issuance_activation_retry_or_receiver_selection():
    source = inspect.getsource(ProductionAppRequestLifecycleOwner.submit)
    assert ".bind(" not in source
    assert ".issue(" not in source
    assert "bootstrap" not in source.lower()
    assert "activation" not in source.lower()
    assert "retry" not in source.lower()
    assert "fallback" not in source.lower()
    assert "kilo" not in source.lower()
    assert "opencode" not in source.lower()
    assert "subprocess" not in source.lower()
    assert "finally:" in source


def test_app_configuration_injects_lifecycle_owner_without_startup_call():
    configure_source = inspect.getsource(app.configure_governed_production_action)
    main_source = inspect.getsource(app.main)
    assert "ProductionAppRequestLifecycleOwner" in configure_source
    assert "ProductionAppRequestLifecycleOwner" not in main_source
    assert ".bind(" not in configure_source
    assert "bootstrap" not in configure_source.lower()
