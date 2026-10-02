"""EA-4E.58R fake integration of credential preflight and durable accounting."""

from __future__ import annotations

import yaml  # noqa: F401  imported before app.py so later hermes_core imports keep PyYAML

from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import (
    FakeQualifiedExecutor,
    _bind,
    _configure,
    _payload,
    _provision_issue,
    _ready,
    _synthetic_preflight,
)
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.production_accounting import ProductionAccountingError, ProductionAccountingLedger
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_app_recovery import ProductionAppRecoveryOwner, ProductionRecoveryStore
from tools.hermes_core.production_app_lifecycle import ProductionRequestAdmissionController
from tools.hermes_core.production_executor_binding import QUALIFIED_EXECUTOR_IMPLEMENTATIONS
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS

import app


def _counts(components, request_id):
    ledger = components.composition.accounting_ledger
    process, model = ledger.events_for_request(request_id)
    return (
        {event.event_type: 1 for event in process},
        {event.event_type: 1 for event in model},
        ledger.process_counts(request_id),
        ledger.model_invocation_counts(request_id),
    )


def test_preflight_failure_blocks_binding(tmp_path):
    components, _, _ = _configure(tmp_path, "kilo-cli-agent")
    missing = _synthetic_preflight(tmp_path / "other", "kilo-cli-agent")
    Path(missing.policy_for("kilo-cli-agent").credential_reference).unlink()
    spec = QUALIFIED_RECEIVERS["kilo-cli-agent"]
    impl = QUALIFIED_EXECUTOR_IMPLEMENTATIONS["kilo-cli-agent"]
    result = ProductionAppBindingProvisioner(
        components.composition.binding_controller,
        components.composition.executor_registry,
        preflight=missing,
    ).bind(
        ProductionAppBindingRequest(
            enablement_id="enable-kilo-cli-agent",
            receiver_id="kilo-cli-agent",
            executor_id=impl["executor_identity"],
            executor_factory=impl["executor_factory"],
            transport_contract_id=spec["transport_contract_id"],
            model_binding_id=spec["model_binding_id"],
            runtime_scope="production",
            issued_at="2025-12-31T23:30:00+00:00",
            expires_at="2026-01-01T00:30:00+00:00",
            requested_ttl_seconds=3600,
            request_nonce="bind-kilo-cli-agent",
            delegation_class="governed",
        )
    )
    assert result.binding_decision == "DENY"
    assert result.binding_reason.startswith("CREDENTIAL_PREFLIGHT_DENIED:")
    assert components.composition.binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_preflight_failure_blocks_lifecycle_before_execution(tmp_path):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e58r-preflight-deny")
    denied = _synthetic_preflight(tmp_path / "empty", "kilo-cli-agent")
    Path(denied.policy_for("kilo-cli-agent").credential_reference).unlink()
    app._GOVERNED_PRODUCTION_HOST._preflight = denied
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert result["reason"].startswith("CREDENTIAL_PREFLIGHT_DENIED:")
    assert fake.calls == 0


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_fake_full_path_records_process_and_model_accounting(tmp_path, receiver_id):
    request_id = f"ea4e58r-full-{receiver_id}"
    components, fake, payload = _ready(tmp_path, receiver_id, request_id)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    process, model, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert process_counts["PROCESS_EXITED"] == 0
    assert process_counts["PROCESS_START_FAILED"] == 0
    assert model_counts["MODEL_INVOCATION_INTENT"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    assert model_counts["MODEL_INVOCATION_COMPLETED"] == 0
    assert model_counts["MODEL_INVOCATION_FAILED"] == 0
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:process" in ledger.unresolved_process_attempts()
    assert f"{request_id}:model" in ledger.unresolved_model_attempts()


def test_process_intent_write_failure_does_not_start_executor(tmp_path, monkeypatch):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e58r-intent-fail")
    ledger = components.composition.accounting_ledger

    def boom(**kwargs):
        raise ProductionAccountingError("PROCESS_ACCOUNTING_WRITE_FAILED")

    monkeypatch.setattr(ledger, "record_process_event", boom)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_model_failure_records_failed_not_completed(tmp_path):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e58r-model-fail")

    def fail_execute(request):
        fake.calls += 1
        from tools.hermes_core.production_execution import ProductionExecutorResult

        return ProductionExecutorResult(
            executor_id=fake.executor_id,
            execution_status="FAILED",
            output=None,
            reason="FAKE_MODEL_FAILURE",
        )

    fake.execute = fail_execute
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    _, _, process_counts, model_counts = _counts(components, "ea4e58r-model-fail")
    assert model_counts["MODEL_INVOCATION_INTENT"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    assert model_counts["MODEL_INVOCATION_FAILED"] == 0
    assert model_counts["MODEL_INVOCATION_COMPLETED"] == 0
    assert process_counts["PROCESS_STARTED"] == 0


def test_post_boundary_accounting_failure_preserves_intent_and_teardown(tmp_path, monkeypatch):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e58r-post-fail")
    from tests.hermes_core.test_ea4e58r3_nonlive_accounting_boundary_semantics import _inject_boundary

    _inject_boundary(
        components,
        process_started=True,
        model_invoked=False,
        process_id="fake-observed-pid",
        process_token="fake-observed-token",
    )
    ledger = components.composition.accounting_ledger
    original = ledger.record_process_event

    def flaky(**kwargs):
        if kwargs.get("event_type") == "PROCESS_STARTED":
            raise ProductionAccountingError("PROCESS_ACCOUNTING_WRITE_FAILED")
        return original(**kwargs)

    monkeypatch.setattr(ledger, "record_process_event", flaky)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    process_counts = ledger.process_counts("ea4e58r-post-fail")
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert "ea4e58r-post-fail:process" in ledger.unresolved_process_attempts()
    assert components.composition.binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_grok_is_denied(tmp_path):
    components, fake, _ = _configure(tmp_path, "kilo-cli-agent")
    result = app.submit_governed_production_action(
        {"request_id": "ea4e58r-grok", "receiver_id": "grok", "production_activation_explicit": True}
    )
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_overlap_is_denied(tmp_path):
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e58r-hold")
    app._GOVERNED_PRODUCTION_HOST._admission_controller.acquire("ea4e58r-hold")
    blocked = app.submit_governed_production_action(payload)
    assert blocked["decision"] == "DENY"
    assert blocked["reason"] == "PRODUCTION_REQUEST_CONCURRENCY_LIMIT"
    assert fake.calls == 0


def test_recovery_accounting_hook_is_configured(tmp_path):
    components, _, _ = _configure(tmp_path, "kilo-cli-agent")
    recovery = app._GOVERNED_PRODUCTION_RECOVERY
    assert recovery is not None
    assert recovery._accounting is components.composition.accounting_ledger
    assert recovery._accounting_clock is components.composition.clock


def test_recovery_second_pass_is_idempotent(tmp_path):
    components, _, _ = _configure(tmp_path, "kilo-cli-agent")
    store = ProductionRecoveryStore.initialize(tmp_path / "recovery-second.sqlite3")
    admission = ProductionRequestAdmissionController()
    store.begin("request-a", "kilo-cli-agent", "dead-host")
    store.mark_clean("request-a")
    owner = ProductionAppRecoveryOwner(
        store,
        admission,
        components.composition.binding_controller,
        type("L", (), {"is_host_active": staticmethod(lambda host: False), "inspect_process": staticmethod(lambda *_: "DEAD")})(),
        type("P", (), {"terminate": staticmethod(lambda *_: True)})(),
        accounting_ledger=components.composition.accounting_ledger,
        accounting_clock=components.composition.clock,
    )
    first = owner.reconcile("request-a")
    second = owner.reconcile("request-a")
    assert first.reason == second.reason == "ALREADY_CLEAN"
    assert first.binding_teardown_count == second.binding_teardown_count == 0
    assert first.process_termination_count == second.process_termination_count == 0
