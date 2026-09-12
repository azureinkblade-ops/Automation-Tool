"""EA-4E.58 retry fake consolidation of checkpointed preflight + accounting."""

from __future__ import annotations

import yaml  # noqa: F401

import app
from tests.hermes_core.test_ea4e52_nonlive_app_host_integration import _ready
from tests.hermes_core.test_ea4e58r_nonlive_preflight_accounting_integration import _counts
from tests.hermes_core.test_ea4e58r3_nonlive_accounting_boundary_semantics import _inject_boundary


def test_retry_kilo_unknown_observation_preserves_intents(tmp_path):
    request_id = "ea4e58-retry-kilo"
    components, fake, payload = _ready(tmp_path, "kilo-cli-agent", request_id)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert process_counts["PROCESS_START_FAILED"] == 0
    assert model_counts["MODEL_INVOCATION_INTENT"] == 1
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    ledger = components.composition.accounting_ledger
    assert f"{request_id}:process" in ledger.unresolved_process_attempts()
    assert f"{request_id}:model" in ledger.unresolved_model_attempts()
    assert components.composition.binding_controller.get_binding_for_receiver("kilo-cli-agent") is None


def test_retry_opencode_unknown_observation_preserves_intents(tmp_path):
    request_id = "ea4e58-retry-opencode"
    components, fake, payload = _ready(tmp_path, "opencode-cli-agent", request_id)
    result = app.submit_governed_production_action(payload)
    assert result["decision"] == "ALLOW"
    assert fake.calls == 1
    _, _, process_counts, model_counts = _counts(components, request_id)
    assert process_counts["PROCESS_START_INTENT"] == 1
    assert process_counts["PROCESS_STARTED"] == 0
    assert model_counts["MODEL_INVOCATION_ENTERED"] == 0
    assert components.composition.binding_controller.get_binding_for_receiver("opencode-cli-agent") is None


def test_retry_observed_process_without_model(tmp_path):
    request_id = "ea4e58-retry-started"
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


def test_retry_grok_denied(tmp_path):
    components, fake, _ = _ready(tmp_path, "kilo-cli-agent", "ea4e58-retry-hold")
    result = app.submit_governed_production_action(
        {"request_id": "ea4e58-retry-grok", "receiver_id": "grok", "production_activation_explicit": True}
    )
    assert result["decision"] == "DENY"
    assert fake.calls == 0
