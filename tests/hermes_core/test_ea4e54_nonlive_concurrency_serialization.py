"""EA-4E.54 global single-slot lifecycle admission. Fake only."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from threading import Barrier, Event, Lock, Thread

import pytest

from tools.hermes_core.production_app_host import ProductionAppHostResult
from tools.hermes_core.production_app_lifecycle import (
    ProductionAppRequestLifecycleOwner,
    ProductionRequestAdmissionController,
)


@dataclass(frozen=True)
class FakeBinding:
    receiver_id: str


class FakeBindingController:
    def __init__(self, *, teardown_result=True, teardown_error=None):
        self.teardown_result = teardown_result
        self.teardown_error = teardown_error
        self.lookups = []
        self.teardown_calls = []
        self.active_bindings = 0
        self.max_active_bindings = 0
        self._lock = Lock()

    def get_binding_for_receiver(self, receiver_id):
        with self._lock:
            self.lookups.append(receiver_id)
            self.active_bindings += 1
            self.max_active_bindings = max(
                self.max_active_bindings, self.active_bindings
            )
        return FakeBinding(receiver_id)

    def teardown(self, binding):
        with self._lock:
            self.teardown_calls.append(binding)
        if self.teardown_error is not None:
            raise self.teardown_error
        if self.teardown_result:
            with self._lock:
                self.active_bindings -= 1
        return self.teardown_result


class FakeAction:
    def __init__(self, *, result=None, error=None, entered=None, release=None):
        self.result = result or ProductionAppHostResult(
            decision="ALLOW", reason="FAKE_SUCCESS"
        )
        self.error = error
        self.entered = entered
        self.release = release
        self.calls = []

    def submit(self, payload):
        self.calls.append(payload["request_id"])
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(2)
        if self.error is not None:
            raise self.error
        return self.result


class CountingAdmission(ProductionRequestAdmissionController):
    def __init__(self):
        super().__init__()
        self.acquire_calls = []
        self.release_calls = []

    def acquire(self, request_id):
        self.acquire_calls.append(request_id)
        return super().acquire(request_id)

    def release(self, request_id):
        self.release_calls.append(request_id)
        return super().release(request_id)


def _payload(request_id, receiver_id="kilo-cli-agent"):
    return {"request_id": request_id, "receiver_id": receiver_id}


def _owner(*, action=None, controller=None, admission=None):
    return ProductionAppRequestLifecycleOwner(
        action or FakeAction(),
        controller or FakeBindingController(),
        admission or ProductionRequestAdmissionController(),
    )


def test_admission_is_owned_by_explicit_request_id_and_rejects_reentrancy():
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a") is True
    assert admission.owner_request_id == "request-a"
    assert admission.acquire("request-a") is False
    assert admission.acquire("request-b") is False
    assert admission.release("request-b") is False
    assert admission.owner_request_id == "request-a"
    assert admission.release("request-a") is True
    assert admission.owner_request_id is None


def test_missing_request_id_fails_before_binding_lookup():
    controller = FakeBindingController()
    action = FakeAction()
    result = _owner(action=action, controller=controller).submit(
        {"receiver_id": "kilo-cli-agent"}
    )
    assert (result.decision, result.reason) == ("DENY", "MISSING_REQUEST_ID")
    assert action.calls == []
    assert controller.lookups == []


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (ProductionAppHostResult(decision="ALLOW", reason="OK"), None),
        (ProductionAppHostResult(decision="DENY", reason="DENIED"), None),
        (None, RuntimeError("failure")),
        (None, TimeoutError("timeout")),
    ],
)
def test_slot_releases_after_every_governed_terminal_path(result, error):
    admission = CountingAdmission()
    owner = _owner(action=FakeAction(result=result, error=error), admission=admission)
    owner.submit(_payload("request-a"))
    assert admission.owner_request_id is None
    assert admission.acquire_calls == ["request-a"]
    assert admission.release_calls == ["request-a"]
    next_result = owner.submit(_payload("request-b"))
    assert next_result.reason != "PRODUCTION_REQUEST_CONCURRENCY_LIMIT"


@pytest.mark.parametrize(
    ("teardown_result", "teardown_error", "reason"),
    [
        (False, None, "BINDING_TEARDOWN_NOT_CONFIRMED"),
        (True, RuntimeError("cleanup"), "BINDING_TEARDOWN_EXCEPTION:RuntimeError"),
    ],
)
def test_slot_releases_when_binding_teardown_fails(
    teardown_result, teardown_error, reason
):
    admission = CountingAdmission()
    controller = FakeBindingController(
        teardown_result=teardown_result,
        teardown_error=teardown_error,
    )
    result = _owner(controller=controller, admission=admission).submit(
        _payload("request-a")
    )
    assert result.reason == reason
    assert admission.owner_request_id is None
    assert admission.acquire_calls == ["request-a"]
    assert admission.release_calls == ["request-a"]
    assert len(controller.teardown_calls) == 1


def test_slot_releases_when_binding_is_missing():
    class MissingBindingController(FakeBindingController):
        def get_binding_for_receiver(self, receiver_id):
            self.lookups.append(receiver_id)
            return None

    admission = CountingAdmission()
    result = _owner(
        controller=MissingBindingController(), admission=admission
    ).submit(_payload("request-a"))
    assert result.reason == "MISSING_EXPLICIT_BINDING"
    assert admission.owner_request_id is None
    assert admission.acquire_calls == ["request-a"]
    assert admission.release_calls == ["request-a"]


@pytest.mark.parametrize(
    ("first_receiver", "second_receiver"),
    [
        ("kilo-cli-agent", "kilo-cli-agent"),
        ("kilo-cli-agent", "opencode-cli-agent"),
        ("opencode-cli-agent", "kilo-cli-agent"),
        ("opencode-cli-agent", "opencode-cli-agent"),
    ],
)
def test_second_concurrent_request_fails_closed_globally(
    first_receiver, second_receiver
):
    entered = Event()
    release = Event()
    action = FakeAction(entered=entered, release=release)
    controller = FakeBindingController()
    admission = ProductionRequestAdmissionController()
    owner = _owner(action=action, controller=controller, admission=admission)
    first_result = []

    thread = Thread(
        target=lambda: first_result.append(
            owner.submit(_payload("request-a", first_receiver))
        )
    )
    thread.start()
    assert entered.wait(2)

    second = owner.submit(_payload("request-b", second_receiver))
    assert (second.decision, second.reason) == (
        "DENY",
        "PRODUCTION_REQUEST_CONCURRENCY_LIMIT",
    )
    assert action.calls == ["request-a"]
    assert controller.lookups == [first_receiver]
    assert controller.active_bindings == 1
    assert controller.max_active_bindings == 1
    assert admission.owner_request_id == "request-a"

    release.set()
    thread.join(2)
    assert not thread.is_alive()
    assert first_result[0].decision == "ALLOW"
    assert admission.owner_request_id is None
    assert controller.active_bindings == 0

    third = owner.submit(_payload("request-c", second_receiver))
    assert third.decision == "ALLOW"
    assert action.calls == ["request-a", "request-c"]
    assert controller.max_active_bindings == 1


def test_reentrant_submission_is_denied_without_nested_binding_lookup():
    controller = FakeBindingController()
    nested_results = []
    owner = None

    class ReentrantAction(FakeAction):
        def submit(self, payload):
            self.calls.append(payload["request_id"])
            nested_results.append(owner.submit(_payload("request-a")))
            return self.result

    action = ReentrantAction()
    owner = _owner(action=action, controller=controller)
    result = owner.submit(_payload("request-a"))
    assert result.decision == "ALLOW"
    assert nested_results[0].reason == "PRODUCTION_REQUEST_CONCURRENCY_LIMIT"
    assert controller.lookups == ["kilo-cli-agent"]


def test_grok_concurrent_request_is_denied_without_fallback_or_action():
    entered = Event()
    release = Event()
    action = FakeAction(entered=entered, release=release)
    controller = FakeBindingController()
    admission = ProductionRequestAdmissionController()
    owner = _owner(action=action, controller=controller, admission=admission)
    thread = Thread(target=lambda: owner.submit(_payload("request-a")))
    thread.start()
    assert entered.wait(2)

    result = owner.submit(_payload("request-grok", "grok"))
    assert (result.decision, result.reason) == (
        "DENY",
        "PRODUCTION_REQUEST_CONCURRENCY_LIMIT",
    )
    assert action.calls == ["request-a"]
    assert controller.lookups == ["kilo-cli-agent"]

    release.set()
    thread.join(2)
    assert not thread.is_alive()


def test_barrier_race_has_exactly_one_admission_owner():
    admission = ProductionRequestAdmissionController()
    barrier = Barrier(17)
    results = []
    result_lock = Lock()

    def contend(index):
        barrier.wait()
        acquired = admission.acquire(f"request-{index}")
        with result_lock:
            results.append(acquired)

    threads = [Thread(target=contend, args=(index,)) for index in range(16)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()

    assert results.count(True) == 1
    assert results.count(False) == 15
    owner_id = admission.owner_request_id
    assert owner_id is not None
    assert admission.release(owner_id) is True


def test_release_boundary_has_no_stale_or_double_owner():
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a") is True
    assert admission.acquire("request-b") is False
    assert admission.release("request-a") is True
    assert admission.acquire("request-c") is True
    assert admission.owner_request_id == "request-c"
    assert admission.acquire("request-d") is False
    assert admission.release("request-c") is True
    assert admission.owner_request_id is None


def test_concurrency_layer_has_no_governance_or_runtime_capability():
    source = inspect.getsource(ProductionRequestAdmissionController)
    lifecycle_source = inspect.getsource(ProductionAppRequestLifecycleOwner.submit)
    lowered = source.lower()
    assert "subprocess" not in lowered
    assert ".bind(" not in lowered
    assert ".issue(" not in lowered
    assert "bootstrap" not in lowered
    assert "activation" not in lowered
    assert "retry" not in lowered
    assert "fallback" not in lowered
    assert "failover" not in lowered
    assert "kilo" not in lowered
    assert "opencode" not in lowered
    assert "grok" not in lowered
    assert "finally:" in lifecycle_source
