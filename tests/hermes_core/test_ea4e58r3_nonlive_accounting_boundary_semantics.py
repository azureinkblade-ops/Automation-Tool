"""EA-4E.58R3 fake accounting-boundary observation semantics."""

from __future__ import annotations

import yaml  # noqa: F401  imported before app.py so later hermes_core imports keep PyYAML

from types import SimpleNamespace

import app
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready
from tests.hermes_core.test_ea4e58r_nonlive_preflight_accounting_integration import _counts


def _boundary_result(**overrides):
    payload = {
        "receiver_id": "kilo-cli-agent",
        "route_decision": "SELECTED",
        "authority_valid": True,
        "activation_valid": True,
        "adapter_resolution": "FAKE",
        "execution_decision": "EXECUTE",
        "executor_called": True,
        "executor_id": "fake-kilo-executor",
        "execution_status": "SUCCESS",
        "real_adapter_called": False,
        "process_started": False,
        "model_invoked": False,
        "reason": "FAKE_BOUNDARY",
        "attempt_count": 1,
        "executor_output": "EA4E58R3_FAKE",
        "process_id": None,
        "process_token": None,
        "process_start_failed": False,
        "process_exited": False,
        "model_invocation_completed": False,
        "model_invocation_failed": False,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _inject_boundary(components, **overrides):
    runtime = components.composition.runtime
    injected = _boundary_result(**overrides)

    def execute(**_kwargs):
        return injected

    runtime._boundary.execute = execute
    return injected


def test_executor_called_without_process_start(tmp_path):
    request_id = "ea4e58r3-called-no-start"
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert process_counts["PROCESS_START_FAILED"] == 0
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:process" in ledger.unresolved_process_attempts()


def test_process_started_model_not_invoked(tmp_path):
    request_id = "ea4e58r3-started-no-model"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        process_started=True,
        model_invoked=False,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_STARTED"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    assert model_counts["MODEL_INVOCATION_INTENT"] == 1
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:model" in ledger.unresolved_model_attempts()


def test_process_and_model_observed(tmp_path):
    request_id = "ea4e58r3-observed-both"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        process_started=True,
        model_invoked=True,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_STARTED"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 1
    assert model_counts["MODEL_INVOCATION_COMPLETED"] == 0
    assert model_counts["MODEL_INVOCATION_FAILED"] == 0


def test_process_start_failure(tmp_path):
    request_id = "ea4e58r3-start-failed"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        executor_called=False,
        process_started=False,
        process_start_failed=True,
        execution_decision="DENY",
        execution_status=None,
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert process_counts["PROCESS_START_FAILED"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0


def test_process_start_unknown(tmp_path):
    request_id = "ea4e58r3-start-unknown"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(components, executor_called=True, process_started=False)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, process_counts, _ = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert process_counts["PROCESS_START_FAILED"] == 0
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:process" in ledger.unresolved_process_attempts()


def test_model_entry_unknown(tmp_path):
    request_id = "ea4e58r3-model-unknown"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        process_started=True,
        model_invoked=False,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, _, model_counts = _counts(components, request_id)
    assert model_counts["MODEL_INVOCATION_INTENT"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:model" in ledger.unresolved_model_attempts()


def test_model_observed_failure(tmp_path):
    request_id = "ea4e58r3-model-failed"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        process_started=True,
        model_invoked=True,
        model_invocation_failed=True,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, _, model_counts = _counts(components, request_id)
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 1
    assert model_counts["MODEL_INVOCATION_FAILED"] == 1
    assert model_counts["MODEL_INVOCATION_COMPLETED"] == 0


def test_model_observed_completion(tmp_path):
    request_id = "ea4e58r3-model-completed"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    _inject_boundary(
        components,
        process_started=True,
        model_invoked=True,
        model_invocation_completed=True,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, _, model_counts = _counts(components, request_id)
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 1
    assert model_counts["MODEL_INVOCATION_COMPLETED"] == 1
    assert model_counts["MODEL_INVOCATION_FAILED"] == 0


def test_no_real_process_id_on_default_path(tmp_path):
    request_id = "ea4e58r3-no-real-pid"
    components, _, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    process_events, model_events = components.composition.accounting_ledger.events_for_request(request_id)
    assert process_events
    assert all(event.process_id is None for event in process_events)
    assert all(event.process_token is None for event in process_events)
    assert all(event.process_id is None for event in model_events)
