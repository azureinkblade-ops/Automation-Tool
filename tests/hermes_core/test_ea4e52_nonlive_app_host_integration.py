"""EA-4E.52 real app.py host integration. Strictly fake and non-live."""

from __future__ import annotations

from dataclasses import asdict
from io import BytesIO
import inspect
import json

import pytest

import app
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tools.hermes_core.production_app_binding import (
    ProductionAppBindingProvisioner,
    ProductionAppBindingRequest,
)
from tools.hermes_core.production_app_config import ProductionAppRuntimeConfig
from tools.hermes_core.production_app_invocation_authorization import (
    ProductionAppInvocationAuthorizationProvisioner,
    ProductionAppInvocationAuthorizationRequest,
)
from tools.hermes_core.production_execution import ProductionExecutorResult
from tools.hermes_core.production_executor_binding import (
    BindingClock,
    ExecutorRegistry,
    QUALIFIED_EXECUTOR_IMPLEMENTATIONS,
)
from tools.hermes_core.production_invocation_auth_store_bootstrap import (
    ProductionInvocationAuthStoreBootstrapRequest,
    ProductionInvocationAuthStoreBootstrapper,
)
from tools.hermes_core.production_invocation_authorization_issuer import (
    ProductionInvocationAuthorizationIssueRequest,
)
from tools.hermes_core.production_issuance import ClockCollaborator, QUALIFIED_RECEIVERS
from tools.hermes_core.production_wiring import ProductionWiringConfig


NOW = "2026-01-01T00:00:00+00:00"
ISSUED = "2025-12-31T23:30:00+00:00"
EXPIRES = "2026-01-01T00:30:00+00:00"


class FakeQualifiedExecutor:
    def __init__(self, receiver_id: str) -> None:
        self.receiver_id = receiver_id
        self.executor_id = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]["executor_identity"]
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ProductionExecutorResult(
            executor_id=self.executor_id,
            execution_status="SUCCESS",
            output=f"EA4E52_FAKE_{self.receiver_id}",
            reason="FAKE_EXECUTION",
        )


@pytest.fixture(autouse=True)
def reset_app_host(monkeypatch):
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_COMPONENTS", None)
    monkeypatch.setattr(app, "_GOVERNED_PRODUCTION_HOST", None)


def _bootstrap_store(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store_path = tmp_path / "ea4e52.auth.sqlite"
    anchor_path = tmp_path / "ea4e52.auth.anchor"
    result = ProductionInvocationAuthStoreBootstrapper().bootstrap(
        ProductionInvocationAuthStoreBootstrapRequest(
            store_path=store_path,
            anchor_path=anchor_path,
            bootstrap_explicit=True,
        )
    )
    assert result.bootstrap_decision == "INITIALIZED"
    return store_path, anchor_path


def _configure(tmp_path, receiver_id: str, *, gate="ENABLED", master="ENABLED"):
    store_path, anchor_path = _bootstrap_store(tmp_path)
    fake = FakeQualifiedExecutor(receiver_id)
    registry = ExecutorRegistry()
    registry.register(receiver_id, fake)
    clock = ClockCollaborator(now=NOW)
    components = app.configure_governed_production_action(
        ProductionAppRuntimeConfig(
            wiring=ProductionWiringConfig(
                master_enable=master,
                auth_store_path=store_path,
                auth_anchor_path=anchor_path,
            ),
            clock=clock,
            callsite_feature_gate=gate,
            executor_registry=registry,
            register_real_executors=False,
        )
    )
    return components, fake, clock


def _bind(components, receiver_id: str):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    impl = QUALIFIED_EXECUTOR_IMPLEMENTATIONS[receiver_id]
    return ProductionAppBindingProvisioner(
        components.composition.binding_controller,
        components.composition.executor_registry,
    ).bind(
        ProductionAppBindingRequest(
            enablement_id=f"enable-{receiver_id}",
            receiver_id=receiver_id,
            executor_id=impl["executor_identity"],
            executor_factory=impl["executor_factory"],
            transport_contract_id=spec["transport_contract_id"],
            model_binding_id=spec["model_binding_id"],
            runtime_scope="production",
            issued_at=ISSUED,
            expires_at=EXPIRES,
            requested_ttl_seconds=3600,
            request_nonce=f"bind-{receiver_id}",
            delegation_class="governed",
        )
    )


def _provision_issue(receiver_id, request_id, authority, handle):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    return ProductionAppInvocationAuthorizationProvisioner(BindingClock(now=NOW)).provision(
        ProductionAppInvocationAuthorizationRequest(
            issue_request_id=f"issue-{request_id}",
            execution_request_id=request_id,
            receiver_id=receiver_id,
            execution_authority=authority,
            binding_handle=handle,
            transport_contract_id=spec["transport_contract_id"],
            model_binding_id=spec["model_binding_id"],
            runtime_scope="production",
            requested_operation="receiver-dispatch",
            requested_ttl_seconds=60,
            attempt_number=1,
            nonce=f"inv-{request_id}",
            delegation_class="governed",
        )
    )


def _payload(receiver_id, request_id, authority, activation, issue):
    spec = QUALIFIED_RECEIVERS[receiver_id]
    return {
        "request_id": request_id,
        "receiver_id": receiver_id,
        "operation": "receiver-dispatch",
        "runtime_scope": "production",
        "task_payload": "EA4E52_FAKE_E2E",
        "production_activation_explicit": True,
        "execution_authority": asdict(authority) if authority is not None else None,
        "activation": asdict(activation) if activation is not None else None,
        "authorization_issue_request": asdict(issue) if issue is not None else None,
        "transport_contract_id": spec["transport_contract_id"],
        "model_binding_id": spec["model_binding_id"],
    }


def _ready(tmp_path, receiver_id: str, request_id: str):
    components, fake, clock = _configure(tmp_path, receiver_id)
    binding = _bind(components, receiver_id)
    assert binding.binding_decision == "BOUND"
    authority, activation = external_authority_and_activation(
        receiver_id, request_id, clock=clock
    )
    provisioned = _provision_issue(receiver_id, request_id, authority, binding.handle)
    assert provisioned.provisioning_decision == "PROVISIONED"
    return components, fake, _payload(
        receiver_id, request_id, authority, activation, provisioned.issue_request
    )


def test_import_and_startup_leave_host_unconfigured_and_inert():
    assert app._GOVERNED_PRODUCTION_COMPONENTS is None
    assert app._GOVERNED_PRODUCTION_HOST is None
    assert "configure_governed_production_action" not in inspect.getsource(app.main)
    result = app.submit_governed_production_action({})
    assert result["decision"] == "DENY"
    assert result["reason"] == "MISSING_GOVERNED_ACTION_DEPENDENCY"


def test_app_route_is_registered_without_startup_configuration():
    source = inspect.getsource(app.Handler.do_POST)
    assert '"/api/governed-production-action"' in source
    assert "submit_governed_production_action(body)" in source


def test_real_http_handler_dispatches_to_injected_fake_governed_action(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-http")
    encoded = json.dumps(payload).encode("utf-8")
    captured = {}
    handler = object.__new__(app.Handler)
    handler.path = "/api/governed-production-action"
    handler.headers = {"Content-Length": str(len(encoded))}
    handler.rfile = BytesIO(encoded)
    handler.send_json = lambda result, status=200: captured.update(
        result=result, status=status
    )

    handler.do_POST()

    assert captured["status"] == 200
    assert captured["result"]["decision"] == "ALLOW"
    assert captured["result"]["receiverId"] == "kilo-cli-agent"
    assert fake.calls == 1


def test_host_configuration_cannot_auto_register_real_executors(tmp_path):
    store_path, anchor_path = _bootstrap_store(tmp_path)
    with pytest.raises(ValueError, match="APP_HOST_REAL_EXECUTOR_AUTO_REGISTRATION_FORBIDDEN"):
        app.configure_governed_production_action(
            ProductionAppRuntimeConfig(
                wiring=ProductionWiringConfig(
                    auth_store_path=store_path,
                    auth_anchor_path=anchor_path,
                ),
                clock=ClockCollaborator(now=NOW),
                register_real_executors=True,
            )
        )


def test_host_configuration_requires_prepared_store(tmp_path):
    registry = ExecutorRegistry()
    registry.register("kilo-cli-agent", FakeQualifiedExecutor("kilo-cli-agent"))
    with pytest.raises(Exception):
        app.configure_governed_production_action(
            ProductionAppRuntimeConfig(
                wiring=ProductionWiringConfig(
                    auth_store_path=tmp_path / "missing.sqlite",
                    auth_anchor_path=tmp_path / "missing.anchor",
                ),
                clock=ClockCollaborator(now=NOW),
                executor_registry=registry,
                register_real_executors=False,
            )
        )
    assert app._GOVERNED_PRODUCTION_HOST is None


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_fake_dual_receiver_host_path(tmp_path, receiver_id):
    _, fake, payload = _ready(tmp_path, receiver_id, f"ea4e52-{receiver_id}")
    result = app.submit_governed_production_action(payload)
    assert result["ok"] is True
    assert result["decision"] == "ALLOW"
    assert result["receiverId"] == receiver_id
    assert result["execution"]["executorCalled"] is True
    assert result["execution"]["status"] == "SUCCESS"
    assert fake.calls == 1


@pytest.mark.parametrize("receiver_id", [None, "", "unknown-agent", "grok"])
def test_missing_unknown_and_grok_receivers_fail_closed(tmp_path, receiver_id):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-bad-receiver")
    payload["receiver_id"] = receiver_id
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_task_text_cannot_select_receiver(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-no-infer")
    payload["receiver_id"] = None
    payload["task_payload"] = "Run kilo-cli-agent using its configured model"
    result = app.submit_governed_production_action(payload)
    assert result["reason"] == "MISSING_RECEIVER"
    assert fake.calls == 0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("request_id", None, "MISSING_REQUEST_ID"),
        ("operation", "other", "INVALID_OPERATION"),
        ("runtime_scope", "lab", "INVALID_RUNTIME_SCOPE"),
        ("production_activation_explicit", False, "APPLICATION_ACTIVATION_INTENT_FALSE"),
    ],
)
def test_incomplete_or_invalid_host_envelope_fails_closed(
    tmp_path, field, value, reason
):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", f"ea4e52-invalid-{field}")
    payload[field] = value
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert result["reason"] == reason
    assert fake.calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_authority", None),
        ("activation", None),
        ("authorization_issue_request", None),
    ],
)
def test_required_governance_artifacts_fail_closed(tmp_path, field, value):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", f"ea4e52-missing-{field}")
    payload[field] = value
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_denied_authority_fails_closed(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-denied-auth")
    payload["execution_authority"]["decision"] = "DENIED"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_disabled_activation_fails_closed(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-disabled-act")
    payload["activation"]["activation_mode"] = "DISABLED"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_receiver_mismatch_fails_closed(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-mismatch")
    payload["execution_authority"]["receiver_id"] = "opencode-cli-agent"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_binding_mismatch_fails_closed(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-binding-mismatch")
    payload["authorization_issue_request"]["binding_id"] = "wrong-binding"
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_missing_binding_fails_closed(tmp_path):
    _, fake, clock = _configure(tmp_path, "kilo-cli-agent")
    authority, activation = external_authority_and_activation(
        "kilo-cli-agent", "ea4e52-no-binding", clock=clock
    )
    issue = ProductionInvocationAuthorizationIssueRequest(
        issue_request_id="issue-no-binding",
        execution_request_id="ea4e52-no-binding",
        receiver_id="kilo-cli-agent",
        binding_id="absent-binding",
        enablement_id="absent-enablement",
        nonce="no-binding",
    )
    result = app.submit_governed_production_action(
        _payload("kilo-cli-agent", "ea4e52-no-binding", authority, activation, issue)
    )
    assert result["decision"] == "DENY"
    assert fake.calls == 0


def test_feature_gate_disabled_and_enabled_alone_cannot_execute(tmp_path):
    _, fake, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-gate")
    payload["execution_authority"] = None
    payload["activation"] = None
    payload["authorization_issue_request"] = None
    assert app.submit_governed_production_action(payload)["decision"] == "DENY"
    assert fake.calls == 0

    components, disabled_fake, clock = _configure(
        tmp_path / "disabled", "kilo-cli-agent", gate="DISABLED"
    )
    binding = _bind(components, "kilo-cli-agent")
    authority, activation = external_authority_and_activation(
        "kilo-cli-agent", "ea4e52-gate-disabled", clock=clock
    )
    provisioned = _provision_issue(
        "kilo-cli-agent", "ea4e52-gate-disabled", authority, binding.handle
    )
    disabled_payload = _payload(
        "kilo-cli-agent",
        "ea4e52-gate-disabled",
        authority,
        activation,
        provisioned.issue_request,
    )
    result = app.submit_governed_production_action(disabled_payload)
    assert result["reason"] == "OUTER_FEATURE_GATE_DISABLED"
    assert disabled_fake.calls == 0


def test_host_does_not_issue_bind_bootstrap_retry_or_select_receiver():
    configure_source = inspect.getsource(app.configure_governed_production_action)
    submit_source = inspect.getsource(app.submit_governed_production_action)
    combined = configure_source + submit_source
    assert "bootstrap" not in combined
    assert ".bind(" not in combined
    assert ".issue(" not in combined
    assert "retry" not in combined.lower()
    assert "fallback" not in combined.lower()
    assert "default_receiver" not in combined
    assert "ProductionAppFactory.build" in configure_source
    assert "host.submit(payload)" in submit_source


def test_public_response_excludes_governance_and_store_internals(tmp_path):
    _, _, payload = _ready(tmp_path, "kilo-cli-agent", "ea4e52-public")
    result = app.submit_governed_production_action(payload)
    rendered = repr(result)
    assert "authorization" not in rendered.lower()
    assert "binding_id" not in rendered
    assert "nonce" not in rendered
    assert "store" not in rendered.lower()
