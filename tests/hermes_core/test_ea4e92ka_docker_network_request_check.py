"""Candidate network bytes can match without becoming Docker authority."""

from copy import deepcopy

import pytest

from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
from tools.hermes_core.agent_local_docker_network_request_check import (
    check_network_create_issue_request,
)
from tools.hermes_core.agent_local_kilo_network_issue_request import (
    build_kilo_network_issue_request,
)
from tools.hermes_core.hashing import sha256_payload


@pytest.fixture
def candidate():
    labels = {
        "hermes.ea4e.attempt": "attempt-1",
        "hermes.ea4e.candidate_sha256": "2" * 64,
        "hermes.ea4e.profile": "FAKE_ONLY_LOCAL_CONTAINER",
        "hermes.ea4e.cleanup_owner": "ea4e-kilo-owner-" + "4" * 32,
    }
    request = {
        "schema_id": "hermes.agent-local-kilo-network-issue-request/v1",
        "action": "network_create",
        "attempt_id": "attempt-1",
        "intent_hash": "1" * 64,
        "candidate_hash": "2" * 64,
        "spec_hash": "3" * 64,
        "governing_commit": "a" * 64,
        "docker_executable_sha256": "b" * 64,
        "docker_engine_endpoint": "npipe:////./pipe/dockerDesktopLinuxEngine",
        "network_name": "ea4e-kilo-" + "5" * 32,
        "network_driver": "bridge",
        "network_internal": True,
        "labels": labels,
        "argv": ["network", "create", "--driver", "bridge", "--internal",
                 "--label", "hermes.ea4e.attempt=attempt-1",
                 "--label", "hermes.ea4e.candidate_sha256=" + "2" * 64,
                 "--label", "hermes.ea4e.cleanup_owner=ea4e-kilo-owner-" + "4" * 32,
                 "--label", "hermes.ea4e.profile=FAKE_ONLY_LOCAL_CONTAINER",
                 "ea4e-kilo-" + "5" * 32],
        "operator_id": "operator-candidate",
        "nonce": "once",
        "requested_ttl_seconds": 60,
        "operator_verified": False,
        "issue_authorized": False,
        "create_authorized": False,
        "launch_authorized": False,
    }
    request["request_hash"] = sha256_payload(request)
    expected = {
        "expected_request_hash": request["request_hash"],
        "expected_commit": "a" * 64,
        "expected_docker_sha256": "b" * 64,
        "expected_attempt_id": "attempt-1",
        "expected_operator_id": "operator-candidate",
        "expected_network_name": "ea4e-kilo-" + "5" * 32,
        "expected_labels": labels,
    }
    return request, expected


def test_exact_candidate_matches_without_authorizing(candidate):
    request, expected = candidate
    result = check_network_create_issue_request(request, **expected)
    assert result.matches is True
    assert result.reason == "REQUEST_BYTES_MATCH_ONLY"


@pytest.mark.parametrize("field,value", [
    ("action", "gateway_create"),
    ("network_internal", False),
    ("docker_engine_endpoint", "tcp://localhost:2375"),
    ("issue_authorized", True),
    ("operator_verified", True),
    ("requested_ttl_seconds", 301),
    ("requested_ttl_seconds", True),
    ("nonce", ""),
    ("intent_hash", "invalid"),
])
def test_mutation_denied_even_with_recomputed_hash(candidate, field, value):
    request, expected = candidate
    request[field] = value
    request["request_hash"] = sha256_payload({
        key: item for key, item in request.items() if key != "request_hash"
    })
    assert not check_network_create_issue_request(request, **expected).matches


@pytest.mark.parametrize("field,value", [
    ("expected_commit", "c" * 64),
    ("expected_docker_sha256", "d" * 64),
    ("expected_attempt_id", "other"),
    ("expected_operator_id", "other"),
    ("expected_network_name", "other"),
    ("expected_labels", {}),
    ("expected_request_hash", "f" * 64),
])
def test_independent_expectation_mismatch_denied(candidate, field, value):
    request, expected = candidate
    expected[field] = value
    assert not check_network_create_issue_request(request, **expected).matches


def test_extra_field_and_modified_argv_denied(candidate):
    request, expected = candidate
    request["authorization_id"] = "forged"
    assert not check_network_create_issue_request(request, **expected).matches
    del request["authorization_id"]
    request["argv"][2] = "--host"
    assert not check_network_create_issue_request(request, **expected).matches


@pytest.mark.parametrize("label,value", [
    ("hermes.ea4e.profile", "PRODUCTION"),
    ("hermes.ea4e.attempt", "other-attempt"),
    ("hermes.ea4e.cleanup_owner", "caller-owned"),
])
def test_self_consistent_but_out_of_policy_labels_denied(candidate, label, value):
    request, expected = candidate
    request["labels"][label] = value
    expected["expected_labels"] = deepcopy(request["labels"])
    argv = ["network", "create", "--driver", "bridge", "--internal"]
    for key, item in sorted(request["labels"].items()):
        argv.extend(("--label", f"{key}={item}"))
    argv.append(request["network_name"])
    request["argv"] = argv
    request["request_hash"] = sha256_payload({
        key: item for key, item in request.items() if key != "request_hash"
    })
    expected["expected_request_hash"] = request["request_hash"]
    assert check_network_create_issue_request(request, **expected).reason == (
        "FAKE_NETWORK_PROFILE_MISMATCH"
    )


def test_existing_builder_candidate_accepted_as_data(tmp_path):
    start, values, spec, _, _, _ = setup(tmp_path)
    try:
        request = build_kilo_network_issue_request(
            values["records"].intents, values["attempt_id"], values["v1_plan"],
            values["prepared"], spec, governing_commit="a" * 64,
            docker_executable_sha256="b" * 64,
            operator_id="operator-candidate", nonce="once",
            requested_ttl_seconds=60,
        )
        expected = {
            "expected_request_hash": request["request_hash"],
            "expected_commit": "a" * 64,
            "expected_docker_sha256": "b" * 64,
            "expected_attempt_id": values["attempt_id"],
            "expected_operator_id": "operator-candidate",
            "expected_network_name": spec["network"]["name"],
            "expected_labels": deepcopy(request["labels"]),
        }
        assert check_network_create_issue_request(request, **expected).matches
    finally:
        start.close()
