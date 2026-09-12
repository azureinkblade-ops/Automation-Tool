"""EA-4E.65 request-scoped activation-only ceremony, fake and non-live."""

from __future__ import annotations

from dataclasses import asdict
import inspect

import app
from tests.hermes_core.ea4e26r_test_support import external_authority_and_activation
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import (
    _bind,
    _configure,
)
from tools.hermes_core.production_issuance import QUALIFIED_RECEIVERS


RECEIVER = "kilo-cli-agent"
GOVERNING_COMMIT = "d61945f96e11b19ef0dcbd008c4d301647c8acad"


def _ready_activation_only(tmp_path, request_id: str):
    components, fake, clock = _configure(tmp_path, RECEIVER)
    binding = _bind(components, RECEIVER)
    assert binding.binding_decision == "BOUND"
    authority, activation = external_authority_and_activation(
        RECEIVER, request_id, clock=clock
    )
    spec = QUALIFIED_RECEIVERS[RECEIVER]
    issued = app.issue_production_activation_authorization(
        {
            "request_id": request_id,
            "receiver_id": RECEIVER,
            "governing_commit": GOVERNING_COMMIT,
            "router_contract_id": activation.router_contract_id,
            "authority_contract_id": activation.authority_contract_id,
            "transport_contract_id": spec["transport_contract_id"],
            "model_binding_id": spec["model_binding_id"],
            "feature_gate_state": "ENABLED",
            "activation_mode": "ENABLED",
            "operator_intent": "EXPLICIT",
            "requested_ttl_seconds": 300,
            "nonce": f"activation-only-{request_id}",
        }
    )
    assert issued["decision"] == "AUTHORIZED"
    payload = {
        "request_id": request_id,
        "receiver_id": RECEIVER,
        "execution_authority": asdict(authority),
        "activation": asdict(activation),
        "activation_authorization": issued["authorization"],
        "transport_contract_id": spec["transport_contract_id"],
        "model_binding_id": spec["model_binding_id"],
    }
    return components, fake, payload, issued["authorization"]


def test_activation_only_consumes_audits_and_tears_down_without_execution(tmp_path):
    components, fake, payload, authorization = _ready_activation_only(
        tmp_path, "activation-only-success"
    )
    store = app._GOVERNED_PRODUCTION_ACTIVATION_AUTH_ISSUER._policy.store

    result = app.activate_governed_production_request_scope(payload)

    assert result["decision"] == "ALLOW"
    assert result["reason"] == "PRODUCTION_ACTIVATION_CEREMONY_COMPLETED"
    assert fake.calls == 0
    assert store.state(authorization["activation_authorization_id"]) == "CONSUMED"
    assert [
        event["event_type"] for event in store.events_for_request(payload["request_id"])
    ] == [
        "ACTIVATION_AUTH_REQUESTED",
        "ACTIVATION_AUTH_ISSUED",
        "ACTIVATION_AUTH_CLAIMED",
        "PRODUCTION_ACTIVATION_ENTERED",
        "ACTIVATION_AUTH_CONSUMED",
        "PRODUCTION_ACTIVATION_EXITED",
    ]
    assert store.ceremony_state(authorization["ceremony_id"]) == "COMPLETED"
    assert (
        components.composition.binding_controller.get_binding_for_receiver(RECEIVER)
        is None
    )
    assert not app._GOVERNED_PRODUCTION_RECOVERY._store.has_unresolved()


def test_activation_only_rejects_missing_payload_without_execution(tmp_path):
    _, fake, _ = _configure(tmp_path, RECEIVER)

    result = app.activate_governed_production_request_scope(None)

    assert result["decision"] == "DENY"
    assert result["reason"] == "INVALID_ACTIVATION_CEREMONY_REQUEST"
    assert fake.calls == 0


def test_activation_only_malformed_mapping_cannot_reach_governed_action(tmp_path):
    _, fake, _ = _configure(tmp_path, RECEIVER)

    result = app.activate_governed_production_request_scope({"request_id": "missing-receiver"})

    assert result["decision"] == "DENY"
    assert result["reason"] == "INVALID_ACTIVATION_CEREMONY_REQUEST"
    assert fake.calls == 0
    source = inspect.getsource(app._GOVERNED_PRODUCTION_HOST._activate_only)
    assert "._governed_action.submit(" not in source


def test_normal_submit_path_still_dispatches_fake_executor(tmp_path):
    from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready

    _, fake, payload = _ready(tmp_path, RECEIVER, "activation-only-submit-regression")

    assert app.submit_governed_production_action(payload)["decision"] == "ALLOW"
    assert fake.calls == 1
