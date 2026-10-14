"""A network-create request is bounded data, never a mutation permit."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_kilo_network_issue_request import (
    build_kilo_network_issue_request,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload


def _build(values, spec, **changed):
    inputs = {
        "governing_commit": "a" * 64,
        "docker_executable_sha256": "b" * 64,
        "operator_id": "operator-candidate",
        "nonce": "network-one-shot-candidate",
        "requested_ttl_seconds": 60,
    }
    inputs.update(changed)
    return build_kilo_network_issue_request(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"], spec, **inputs,
    )


def test_exact_network_request_is_stable_and_non_authorizing(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        request = _build(values, spec)
        assert request == _build(values, spec)
        assert request["action"] == "network_create"
        assert request["network_name"] == spec["network"]["name"]
        assert request["labels"]["hermes.ea4e.cleanup_owner"] == spec["cleanup_owner"]
        assert request["argv"][-1] == spec["network"]["name"]
        assert request["argv"][:5] == [
            "network", "create", "--driver", "bridge", "--internal",
        ]
        assert request["request_hash"] == sha256_payload({
            key: value for key, value in request.items() if key != "request_hash"
        })
        for key in (
            "operator_verified", "issue_authorized", "create_authorized",
            "launch_authorized",
        ):
            assert request[key] is False
        assert "authorization_id" not in request
        assert "network_id" not in request
    finally:
        start.close()


@pytest.mark.parametrize("field,value", [
    ("governing_commit", "stale"),
    ("docker_executable_sha256", "B" * 64),
    ("operator_id", " "),
    ("nonce", ""),
    ("requested_ttl_seconds", 0),
    ("requested_ttl_seconds", 301),
    ("requested_ttl_seconds", True),
])
def test_malformed_request_identity_denied(tmp_path, field, value):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError):
            _build(values, spec, **{field: value})
    finally:
        start.close()


def test_changed_network_spec_denied(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        altered = deepcopy(spec)
        altered["network"]["name"] = "other"
        with pytest.raises(DelegationIntegrityError):
            _build(values, altered)
    finally:
        start.close()
