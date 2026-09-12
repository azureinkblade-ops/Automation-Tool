"""EA-4E.55 durable lifecycle recovery qualification. Fake only."""

from __future__ import annotations

from dataclasses import dataclass
import inspect

import pytest

import app
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready
from tools.hermes_core.production_app_host import ProductionAppHostResult
from tools.hermes_core.production_app_lifecycle import (
    ProductionAppRequestLifecycleOwner,
    ProductionRequestAdmissionController,
)
from tools.hermes_core.production_app_recovery import (
    ProductionAppRecoveryOwner,
    ProductionRecoveryError,
    ProductionRecoveryStore,
)


@pytest.fixture(autouse=True)
def reset_app_recovery_state(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_COMPONENTS", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_RECOVERY", None)


@dataclass(frozen=True)
class FakeBinding:
    binding_id: str
    enablement_id: str
    receiver_id: str


class FakeBindingController:
    def __init__(self, binding=None, *, teardown_result=True):
        self.binding = binding
        self.teardown_result = teardown_result
        self.lookups = []
        self.teardown_calls = []

    def get_binding_for_receiver(self, receiver_id):
        self.lookups.append(receiver_id)
        if self.binding is not None and self.binding.receiver_id == receiver_id:
            return self.binding
        return None

    def teardown(self, binding):
        self.teardown_calls.append(binding)
        if self.teardown_result:
            self.binding = None
        return self.teardown_result


class FakeLiveness:
    def __init__(self, *, host_active=False, process_state="DEAD"):
        self.host_active = host_active
        self.process_state = process_state
        self.host_checks = []
        self.process_checks = []

    def is_host_active(self, host_instance_id):
        self.host_checks.append(host_instance_id)
        return self.host_active

    def inspect_process(self, process_id, process_token):
        self.process_checks.append((process_id, process_token))
        return self.process_state


class FakeProcessController:
    def __init__(self, *, result=True):
        self.result = result
        self.termination_calls = []

    def terminate(self, process_id, process_token):
        self.termination_calls.append((process_id, process_token))
        return self.result


class FakeAction:
    def __init__(self):
        self.calls = 0

    def submit(self, payload):
        self.calls += 1
        return ProductionAppHostResult(decision="ALLOW", reason="FAKE_SUCCESS")


def _store(tmp_path):
    return ProductionRecoveryStore.initialize(tmp_path / "production-recovery.sqlite3")


def _stale(
    tmp_path,
    *,
    receiver_id="kilo-cli-agent",
    phase="ADMISSION_ACQUIRED",
    binding=None,
    process_state="NOT_REGISTERED",
):
    store = _store(tmp_path)
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("request-a")
    store.begin("request-a", receiver_id, "crashed-host")
    fields = {"process_state": process_state}
    if binding is not None:
        fields.update(
            binding_id=binding.binding_id,
            enablement_id=binding.enablement_id,
        )
    store.transition("request-a", phase, **fields)
    bindings = FakeBindingController(binding)
    liveness = FakeLiveness()
    processes = FakeProcessController()
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    return store, admission, bindings, liveness, processes, owner


def _binding(receiver_id="kilo-cli-agent"):
    return FakeBinding("binding-a", "enablement-a", receiver_id)


def test_crash_after_admission_clears_only_exact_stale_owner(tmp_path):
    store, admission, bindings, _, processes, owner = _stale(tmp_path)
    result = owner.reconcile("request-a")
    assert (result.decision, result.reason) == ("ALLOW", "RECOVERED")
    assert admission.owner_request_id is None
    assert bindings.teardown_calls == []
    assert processes.termination_calls == []
    assert store.load("request-a").cleanup_state == "CLEAN"


def test_active_host_owner_is_not_recovered(tmp_path):
    store, admission, bindings, _, processes, _ = _stale(tmp_path)
    owner = ProductionAppRecoveryOwner(
        store,
        admission,
        bindings,
        FakeLiveness(host_active=True),
        processes,
    )
    result = owner.reconcile("request-a")
    assert (result.decision, result.reason) == ("DENY", "ACTIVE_LIFECYCLE_OWNER")
    assert admission.owner_request_id == "request-a"
    assert bindings.teardown_calls == []


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_crash_after_binding_tears_down_exact_identity(tmp_path, receiver_id):
    binding = _binding(receiver_id)
    store, admission, bindings, _, processes, owner = _stale(
        tmp_path,
        receiver_id=receiver_id,
        phase="BINDING_OWNED",
        binding=binding,
    )
    result = owner.reconcile("request-a")
    assert result.decision == "ALLOW"
    assert result.binding_teardown_count == 1
    assert bindings.teardown_calls == [binding]
    assert processes.termination_calls == []
    assert admission.owner_request_id is None
    assert store.load("request-a").cleanup_state == "CLEAN"


def test_crash_after_invocation_auth_metadata_recovers_without_reissue(tmp_path):
    binding = _binding()
    store, _, bindings, _, _, owner = _stale(
        tmp_path, phase="BINDING_OWNED", binding=binding
    )
    store.transition(
        "request-a",
        "INVOCATION_AUTH_PERSISTED",
        invocation_authorization_id="issue-request-a",
    )
    result = owner.reconcile("request-a")
    assert result.decision == "ALLOW"
    assert bindings.teardown_calls == [binding]


def test_process_registered_but_not_started_is_not_terminated(tmp_path):
    binding = _binding()
    store, _, bindings, _, processes, owner = _stale(
        tmp_path,
        phase="PROCESS_REGISTERED",
        binding=binding,
        process_state="REGISTERED",
    )
    store.transition(
        "request-a",
        "PROCESS_REGISTERED",
        process_id="pid-a",
        process_token="token-a",
    )
    result = owner.reconcile("request-a")
    assert result.decision == "ALLOW"
    assert processes.termination_calls == []
    assert bindings.teardown_calls == [binding]


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_started_orphan_is_inspected_and_terminated_by_exact_identity(
    tmp_path, receiver_id
):
    binding = _binding(receiver_id)
    store, admission, bindings, _, _, _ = _stale(
        tmp_path,
        receiver_id=receiver_id,
        phase="PROCESS_STARTED",
        binding=binding,
        process_state="STARTED",
    )
    store.transition(
        "request-a",
        "PROCESS_STARTED",
        process_id="pid-a",
        process_token="token-a",
    )
    liveness = FakeLiveness(process_state="ALIVE")
    processes = FakeProcessController()
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    result = owner.reconcile("request-a")
    assert result.decision == "ALLOW"
    assert result.process_termination_count == 1
    assert liveness.process_checks == [("pid-a", "token-a")]
    assert processes.termination_calls == [("pid-a", "token-a")]
    assert bindings.teardown_calls == [binding]
    assert admission.owner_request_id is None


def test_already_dead_process_skips_termination(tmp_path):
    binding = _binding()
    store, admission, bindings, _, processes, _ = _stale(
        tmp_path, phase="PROCESS_STARTED", binding=binding, process_state="STARTED"
    )
    store.transition(
        "request-a", "PROCESS_STARTED", process_id="pid-a", process_token="token-a"
    )
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, FakeLiveness(process_state="DEAD"), processes
    )
    result = owner.reconcile("request-a")
    assert result.decision == "ALLOW"
    assert processes.termination_calls == []


def test_teardown_pending_started_process_is_still_reconciled(tmp_path):
    binding = _binding()
    store, admission, bindings, _, processes, _ = _stale(
        tmp_path, phase="PROCESS_STARTED", binding=binding, process_state="STARTED"
    )
    store.transition(
        "request-a", "PROCESS_STARTED", process_id="pid-a", process_token="token-a"
    )
    store.transition("request-a", "TEARDOWN_PENDING")
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, FakeLiveness(process_state="ALIVE"), processes
    )
    result = owner.reconcile("request-a")
    assert result.process_termination_count == 1
    assert processes.termination_calls == [("pid-a", "token-a")]


def test_process_identity_mismatch_fails_closed_and_blocks_new_work(tmp_path):
    binding = _binding()
    store, admission, bindings, _, processes, _ = _stale(
        tmp_path, phase="PROCESS_STARTED", binding=binding, process_state="STARTED"
    )
    store.transition(
        "request-a", "PROCESS_STARTED", process_id="pid-a", process_token="token-a"
    )
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, FakeLiveness(process_state="MISMATCH"), processes
    )
    result = owner.reconcile("request-a")
    assert (result.decision, result.reason) == (
        "DENY",
        "PROCESS_OWNERSHIP_MISMATCH",
    )
    assert processes.termination_calls == []
    assert bindings.teardown_calls == []
    assert store.load("request-a").cleanup_state == "FAILED"


def test_admission_identity_mismatch_prevents_all_cleanup(tmp_path):
    binding = _binding()
    store, _, bindings, _, processes, _ = _stale(
        tmp_path, phase="PROCESS_STARTED", binding=binding, process_state="STARTED"
    )
    store.transition(
        "request-a", "PROCESS_STARTED", process_id="pid-a", process_token="token-a"
    )
    admission = ProductionRequestAdmissionController()
    assert admission.acquire("different-request")
    liveness = FakeLiveness(process_state="ALIVE")
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    result = owner.reconcile("request-a")
    assert (result.decision, result.reason) == ("DENY", "ADMISSION_OWNER_MISMATCH")
    assert liveness.process_checks == []
    assert processes.termination_calls == []
    assert bindings.teardown_calls == []


def test_binding_identity_mismatch_fails_closed_without_teardown(tmp_path):
    recorded = _binding()
    store, admission, _, liveness, processes, _ = _stale(
        tmp_path, phase="BINDING_OWNED", binding=recorded
    )
    actual = FakeBinding("binding-other", "enablement-a", "kilo-cli-agent")
    bindings = FakeBindingController(actual)
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    result = owner.reconcile("request-a")
    assert (result.decision, result.reason) == (
        "DENY",
        "BINDING_IDENTITY_MISMATCH",
    )
    assert bindings.teardown_calls == []
    assert store.load("request-a").cleanup_state == "FAILED"


def test_recovery_is_idempotent_after_success(tmp_path):
    binding = _binding()
    store, _, bindings, _, processes, owner = _stale(
        tmp_path, phase="BINDING_OWNED", binding=binding
    )
    first = owner.reconcile("request-a")
    second = owner.reconcile("request-a")
    assert (first.decision, second.reason) == ("ALLOW", "ALREADY_CLEAN")
    assert len(bindings.teardown_calls) == 1
    assert processes.termination_calls == []
    assert store.load("request-a").cleanup_state == "CLEAN"


def test_cleanup_failure_is_durable_and_not_retried(tmp_path):
    binding = _binding()
    store, admission, _, liveness, processes, _ = _stale(
        tmp_path, phase="BINDING_OWNED", binding=binding
    )
    bindings = FakeBindingController(binding, teardown_result=False)
    owner = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    first = owner.reconcile("request-a")
    reopened_owner = ProductionAppRecoveryOwner(
        ProductionRecoveryStore(store.path),
        admission,
        bindings,
        liveness,
        processes,
    )
    second = reopened_owner.reconcile("request-a")
    assert first.reason == "BINDING_TEARDOWN_FAILED"
    assert second.reason == "RECOVERY_PREVIOUSLY_FAILED"
    assert len(bindings.teardown_calls) == 1
    assert store.load("request-a").cleanup_state == "FAILED"


def test_lifecycle_blocks_until_successful_explicit_recovery(tmp_path):
    store, admission, bindings, liveness, processes, recovery = _stale(tmp_path)
    action = FakeAction()
    lifecycle = ProductionAppRequestLifecycleOwner(
        action,
        bindings,
        admission,
        store,
        "current-host",
    )
    blocked = lifecycle.submit(
        {"request_id": "request-b", "receiver_id": "kilo-cli-agent"}
    )
    assert blocked.reason == "PRODUCTION_RECOVERY_REQUIRED"
    assert action.calls == 0

    assert recovery.reconcile("request-a").decision == "ALLOW"
    bindings.binding = _binding()
    allowed = lifecycle.submit(
        {"request_id": "request-b", "receiver_id": "kilo-cli-agent"}
    )
    assert allowed.decision == "ALLOW"
    assert store.load("request-b").cleanup_state == "CLEAN"


def test_failed_recovery_keeps_lifecycle_blocked(tmp_path):
    binding = _binding()
    store, admission, _, liveness, processes, _ = _stale(
        tmp_path, phase="BINDING_OWNED", binding=binding
    )
    bindings = FakeBindingController(binding, teardown_result=False)
    recovery = ProductionAppRecoveryOwner(
        store, admission, bindings, liveness, processes
    )
    assert recovery.reconcile("request-a").decision == "DENY"
    action = FakeAction()
    lifecycle = ProductionAppRequestLifecycleOwner(
        action, bindings, admission, store, "current-host"
    )
    result = lifecycle.submit(
        {"request_id": "request-b", "receiver_id": "kilo-cli-agent"}
    )
    assert result.reason == "PRODUCTION_RECOVERY_REQUIRED"
    assert action.calls == 0


def test_grok_recovery_record_is_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ProductionRecoveryError, match="UNSUPPORTED_RECEIVER"):
        store.begin("request-grok", "grok", "crashed-host")


def test_recovery_store_releases_sqlite_handles(tmp_path):
    store = _store(tmp_path)
    store.begin("request-a", "kilo-cli-agent", "host-a")
    assert store.load("request-a") is not None
    moved = store.path.with_suffix(".moved")
    store.path.replace(moved)
    moved.replace(store.path)


def test_unsupported_receiver_is_denied_without_recovery_state(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e55-unsupported")
    payload["receiver_id"] = "grok"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0
    store = ProductionRecoveryStore(tmp_path / "production-recovery.sqlite3")
    assert store.load("ea4e55-unsupported") is None


def test_normal_app_fake_completion_marks_recovery_state_clean(tmp_path):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e55-normal")
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    assert components.composition.binding_controller.active_binding_count == 0
    store = ProductionRecoveryStore(tmp_path / "production-recovery.sqlite3")
    assert store.load("ea4e55-normal").cleanup_state == "CLEAN"


def test_recovery_is_explicit_and_has_no_runtime_capability():
    module_source = inspect.getsource(ProductionAppRecoveryOwner)
    configure_source = inspect.getsource(app.configure_governed_production_action)
    main_source = inspect.getsource(app.main)
    lowered = module_source.lower()
    assert "subprocess" not in lowered
    assert ".issue(" not in lowered
    assert ".bind(" not in lowered
    assert "retry" not in lowered
    assert "fallback" not in lowered
    assert "failover" not in lowered
    assert "reconcile_governed_production_recovery" not in main_source
    assert "ProductionAppRecoveryOwner" in configure_source
