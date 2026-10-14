"""A create issue request is data, never authority or a Docker command."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_kilo_create_issue_request import (
    build_kilo_create_issue_request,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.hashing import sha256_payload
from tools.hermes_core.kilo_fake_gateway_probe_plan import (
    GATEWAY_IMAGE, GATEWAY_INDEX_ID, GATEWAY_PLATFORM_MANIFEST,
)


def _build(values, spec, **changed):
    kwargs = {
        "governing_commit": "a" * 64,
        "docker_executable_sha256": "b" * 64,
        "network_id": "c" * 64,
        "gateway_id": "d" * 64,
        "operator_id": "reviewed-operator-candidate",
        "nonce": "unique-proposal-nonce",
        "requested_ttl_seconds": 60,
    }
    kwargs.update(changed)
    return build_kilo_create_issue_request(
        values["records"].intents, values["attempt_id"],
        values["v1_plan"], values["prepared"], spec, **kwargs,
    )


def test_exact_request_is_stable_and_non_authorizing(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        request = _build(values, spec)
        assert request == _build(values, spec)
        assert request["spec_hash"] == spec["spec_hash"]
        assert request["network_name"] == spec["network"]["name"]
        assert request["schema_id"] == "hermes.agent-local-kilo-create-issue-request/v2"
        assert request["gateway_image"] == GATEWAY_IMAGE
        assert request["gateway_image_index"] == GATEWAY_INDEX_ID
        assert request["gateway_image_manifest"] == GATEWAY_PLATFORM_MANIFEST
        assert request["docker_engine_endpoint"] == (
            "npipe:////./pipe/dockerDesktopLinuxEngine"
        )
        for field in (
            "operator_verified", "network_ownership_verified",
            "gateway_ownership_verified", "issue_authorized",
            "create_authorized", "launch_authorized",
        ):
            assert request[field] is False
        assert request["request_hash"] == sha256_payload({
            key: value for key, value in request.items() if key != "request_hash"
        })
        assert "argv" not in request
        assert "authorization_id" not in request
    finally:
        start.close()


@pytest.mark.parametrize("field,value", [
    ("governing_commit", "stale"),
    ("docker_executable_sha256", "B" * 64),
    ("network_id", ""),
    ("gateway_id", "x" * 64),
    ("operator_id", " "),
    ("nonce", ""),
    ("requested_ttl_seconds", 0),
    ("requested_ttl_seconds", 301),
    ("requested_ttl_seconds", True),
])
def test_malformed_reported_identity_denied(tmp_path, field, value):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        with pytest.raises(DelegationIntegrityError):
            _build(values, spec, **{field: value})
    finally:
        start.close()


def test_changed_create_spec_denied_before_request(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        altered = deepcopy(spec)
        altered["container_name"] = "different"
        with pytest.raises(DelegationIntegrityError):
            _build(values, altered)
    finally:
        start.close()
