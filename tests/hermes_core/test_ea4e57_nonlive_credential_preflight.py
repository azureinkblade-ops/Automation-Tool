"""EA-4E.57 local-only credential readiness qualification."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

from tools.hermes_core.production_credential_preflight import (
    KILO_MODEL_BINDING_ID,
    KILO_TRANSPORT_ID,
    LOCAL_AUTH_STATE_REFERENCE,
    OPENCODE_MODEL_BINDING_ID,
    OPENCODE_TRANSPORT_ID,
    ProductionCredentialReadinessPreflight,
    ReceiverCredentialPolicy,
)


SENTINEL = "EA4E57_SENTINEL_DO_NOT_PRINT"


def _policy(tmp_path, receiver_id="kilo-cli-agent"):
    name = "kilo" if receiver_id == "kilo-cli-agent" else "opencode"
    state = tmp_path / name / f"{name}.db"
    return ReceiverCredentialPolicy(
        receiver_id=receiver_id,
        provider_id=name,
        config_identity=f"hermes-ea4e-{name}-local-auth-state",
        credential_source_type=LOCAL_AUTH_STATE_REFERENCE,
        credential_reference=str(state),
        credential_reference_id=f"{name}-local-auth-state",
        allowed_root=str(tmp_path / name),
        transport_contract_id=(
            KILO_TRANSPORT_ID
            if receiver_id == "kilo-cli-agent"
            else OPENCODE_TRANSPORT_ID
        ),
        model_binding_id=(
            KILO_MODEL_BINDING_ID
            if receiver_id == "kilo-cli-agent"
            else OPENCODE_MODEL_BINDING_ID
        ),
    )


def _config(policy):
    return {
        "receiver_id": policy.receiver_id,
        "credential_receiver_id": policy.receiver_id,
        "provider_id": policy.provider_id,
        "config_identity": policy.config_identity,
        "credential_source_type": policy.credential_source_type,
        "credential_reference": policy.credential_reference,
        "transport_contract_id": policy.transport_contract_id,
        "model_binding_id": policy.model_binding_id,
    }


def _ready(tmp_path, receiver_id="kilo-cli-agent"):
    policy = _policy(tmp_path, receiver_id)
    path = tmp_path / policy.provider_id / f"{policy.provider_id}.db"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic-local-auth-state")
    return ProductionCredentialReadinessPreflight({receiver_id: policy}), policy


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_receiver_ready_fixture_passes_without_secret_output(tmp_path, receiver_id):
    service, policy = _ready(tmp_path, receiver_id)
    result = service.check(_config(policy))
    assert result.ready is True
    assert result.failure_code is None
    assert result.credential_presence == "PRESENT"
    assert result.structural_readiness == "READY"
    assert policy.credential_reference not in json.dumps(result.to_dict())


@pytest.mark.parametrize("receiver_id", ["kilo-cli-agent", "opencode-cli-agent"])
def test_missing_local_auth_state_fails_closed(tmp_path, receiver_id):
    policy = _policy(tmp_path, receiver_id)
    result = ProductionCredentialReadinessPreflight({receiver_id: policy}).check(
        _config(policy)
    )
    assert (result.ready, result.failure_code) == (False, "CREDENTIAL_VALUE_ABSENT")


def test_empty_local_auth_state_fails_closed(tmp_path):
    policy = _policy(tmp_path)
    path = tmp_path / "kilo" / "kilo.db"
    path.parent.mkdir()
    path.touch()
    result = ProductionCredentialReadinessPreflight({policy.receiver_id: policy}).check(
        _config(policy)
    )
    assert result.failure_code == "CREDENTIAL_VALUE_ABSENT"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("credential_receiver_id", "opencode-cli-agent", "RECEIVER_CONFIG_MISMATCH"),
        ("provider_id", "wrong-provider", "PROVIDER_CONFIG_MISMATCH"),
        ("config_identity", "wrong-config", "RECEIVER_CONFIG_MISMATCH"),
        ("model_binding_id", "wrong-model", "MODEL_BINDING_MISMATCH"),
        ("transport_contract_id", "wrong-transport", "TRANSPORT_BINDING_MISMATCH"),
    ],
)
def test_receiver_provider_and_binding_mismatches_fail_closed(
    tmp_path, field, value, reason
):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config[field] = value
    result = service.check(config)
    assert (result.ready, result.failure_code) == (False, reason)


@pytest.mark.parametrize("receiver_id", ["grok", "unknown", ""])
def test_unqualified_receiver_fails_closed(tmp_path, receiver_id):
    policy = _policy(tmp_path)
    config = _config(policy)
    config["receiver_id"] = receiver_id
    result = ProductionCredentialReadinessPreflight({policy.receiver_id: policy}).check(
        config
    )
    assert result.failure_code == "UNQUALIFIED_RECEIVER"


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "credential",
        "credential_value",
        "password",
        "secret",
        "token",
        "access_token",
        "authorization",
        "client_secret",
    ],
)
def test_literal_secret_fields_are_denied_and_redacted(tmp_path, field, capsys):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config[field] = SENTINEL
    result = service.check(config)
    rendered = json.dumps(result.to_dict()) + repr(result) + str(capsys.readouterr())
    assert result.failure_code == "SECRET_LITERAL_FORBIDDEN"
    assert SENTINEL not in rendered


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("credential_source_type", "", "CREDENTIAL_REFERENCE_MISSING"),
        ("credential_source_type", "COMMAND_REFERENCE", "CREDENTIAL_SOURCE_UNSUPPORTED"),
        ("credential_reference", "", "CREDENTIAL_REFERENCE_MISSING"),
        ("credential_reference", "relative.db", "CREDENTIAL_REFERENCE_MALFORMED"),
    ],
)
def test_missing_malformed_and_unsupported_references_fail_closed(
    tmp_path, field, value, reason
):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config[field] = value
    result = service.check(config)
    assert result.failure_code == reason


def test_reference_outside_allowed_root_fails_closed(tmp_path):
    policy = replace(
        _policy(tmp_path),
        credential_reference=str(tmp_path / "outside.db"),
    )
    config = _config(policy)
    result = ProductionCredentialReadinessPreflight({policy.receiver_id: policy}).check(
        config
    )
    assert result.failure_code == "CREDENTIAL_REFERENCE_MALFORMED"


def test_directory_reference_is_not_accepted_as_auth_state(tmp_path):
    policy = _policy(tmp_path)
    path = tmp_path / "kilo" / "kilo.db"
    path.mkdir(parents=True)
    result = ProductionCredentialReadinessPreflight({policy.receiver_id: policy}).check(
        _config(policy)
    )
    assert result.failure_code == "CREDENTIAL_VALUE_ABSENT"


def test_non_mapping_input_fails_closed():
    result = ProductionCredentialReadinessPreflight({}).check(None)
    assert result.failure_code == "PREFLIGHT_INTERNAL_ERROR"


def test_decision_is_deterministic_and_mapping_order_independent(tmp_path):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    reversed_config = dict(reversed(list(config.items())))
    assert service.check(config) == service.check(config)
    assert service.check(config) == service.check(reversed_config)


def test_irrelevant_task_text_does_not_affect_readiness(tmp_path):
    service, policy = _ready(tmp_path)
    first = _config(policy)
    second = {**first, "task_text": "select another receiver using a credential name"}
    assert service.check(first) == service.check(second)


def test_reference_name_and_file_content_do_not_select_receiver(tmp_path):
    service, policy = _ready(tmp_path)
    path = tmp_path / "kilo" / "kilo.db"
    path.write_text("opencode-cli-agent " + SENTINEL, encoding="utf-8")
    result = service.check(_config(policy))
    assert result.receiver_id == "kilo-cli-agent"
    assert SENTINEL not in json.dumps(result.to_dict())


def test_result_has_no_secret_hash_length_path_or_value_fields(tmp_path):
    service, policy = _ready(tmp_path)
    result = service.check(_config(policy)).to_dict()
    assert not ({"value", "secret", "hash", "length", "path"} & set(result))
    assert policy.credential_reference not in json.dumps(result)


def test_service_has_no_cache_or_accounting_state(tmp_path):
    service, _ = _ready(tmp_path)
    assert set(vars(service)) == {"_policies"}


def test_module_has_no_runtime_capability_imports():
    import tools.hermes_core.production_credential_preflight as module

    source = inspect.getsource(module)
    forbidden = (
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "playwright",
        "selenium",
        "oauth",
        "device_code",
        "webbrowser",
    )
    assert all(term not in source.lower() for term in forbidden)


def test_constructing_service_performs_no_file_read(monkeypatch):
    calls = []
    monkeypatch.setattr("pathlib.Path.open", lambda *args, **kwargs: calls.append(args))
    ProductionCredentialReadinessPreflight({})
    assert calls == []


def test_check_does_not_mutate_source(tmp_path):
    service, policy = _ready(tmp_path)
    path = tmp_path / "kilo" / "kilo.db"
    before = path.read_bytes()
    service.check(_config(policy))
    assert path.read_bytes() == before


def test_failure_result_is_safe_for_repr_json_and_exception_context(tmp_path):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config["secret"] = SENTINEL
    result = service.check(config)
    rendered = repr(result) + json.dumps(result.to_dict()) + str(result.failure_code)
    assert SENTINEL not in rendered


def test_literal_secret_field_matching_is_case_insensitive(tmp_path):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config["API_KEY"] = SENTINEL
    result = service.check(config)
    assert result.failure_code == "SECRET_LITERAL_FORBIDDEN"
    assert SENTINEL not in json.dumps(result.to_dict())


def test_unknown_config_field_fails_closed(tmp_path):
    service, policy = _ready(tmp_path)
    config = _config(policy)
    config["unexpected_metadata"] = {"nested": "value"}
    result = service.check(config)
    assert result.failure_code == "PREFLIGHT_INTERNAL_ERROR"


def test_unreadable_source_fails_closed_without_path_or_content(monkeypatch, tmp_path):
    service, policy = _ready(tmp_path)

    def denied_open(*args, **kwargs):
        raise PermissionError("synthetic denied")

    monkeypatch.setattr("pathlib.Path.open", denied_open)
    result = service.check(_config(policy))
    assert result.failure_code == "CREDENTIAL_SOURCE_UNREADABLE"
    assert policy.credential_reference not in json.dumps(result.to_dict())


def test_preflight_makes_no_network_or_process_calls(monkeypatch, tmp_path):
    import socket
    import subprocess

    observed = {"network": 0, "process": 0}

    def network_forbidden(*args, **kwargs):
        observed["network"] += 1
        raise AssertionError("network boundary reached")

    def process_forbidden(*args, **kwargs):
        observed["process"] += 1
        raise AssertionError("process boundary reached")

    monkeypatch.setattr(socket, "socket", network_forbidden)
    monkeypatch.setattr(subprocess, "Popen", process_forbidden)
    monkeypatch.setattr(subprocess, "run", process_forbidden)
    service, policy = _ready(tmp_path)
    assert service.check(_config(policy)).ready is True
    assert observed == {"network": 0, "process": 0}


def test_ready_result_does_not_issue_bind_activate_or_execute(tmp_path):
    service, policy = _ready(tmp_path)
    result = service.check(_config(policy))
    assert result.ready
    assert set(result.to_dict()) == {
        "receiver_id",
        "config_identity_reference",
        "credential_source_type",
        "credential_reference_id",
        "credential_presence",
        "structural_readiness",
        "binding_consistency",
        "failure_code",
        "ready",
    }


def test_failure_can_gate_fake_future_boundary(tmp_path):
    policy = _policy(tmp_path)
    result = ProductionCredentialReadinessPreflight({policy.receiver_id: policy}).check(
        _config(policy)
    )
    fake_boundary_calls = []
    if result.ready:
        fake_boundary_calls.append("called")
    assert fake_boundary_calls == []


def test_default_policies_are_exactly_the_two_qualified_receivers():
    service = ProductionCredentialReadinessPreflight()
    assert set(service._policies) == {"kilo-cli-agent", "opencode-cli-agent"}
    assert all(
        policy.credential_source_type == LOCAL_AUTH_STATE_REFERENCE
        for policy in service._policies.values()
    )
