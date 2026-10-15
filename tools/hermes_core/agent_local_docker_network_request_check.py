"""Pure shape and byte check for a proposed Docker network-create request.

This module has no issuer, store, process, or Docker capability. A matching
request is not an authorization or an operator witness.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_NETWORK = re.compile(r"ea4e-kilo-[0-9a-f]{32}\Z")
_OWNER = re.compile(r"ea4e-kilo-owner-[0-9a-f]{32}\Z")
_ENDPOINT = "npipe:////./pipe/dockerDesktopLinuxEngine"
_LABELS = frozenset({
    "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
    "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
})
_FIELDS = frozenset({
    "schema_id", "action", "attempt_id", "intent_hash", "candidate_hash",
    "spec_hash", "governing_commit", "docker_executable_sha256",
    "docker_engine_endpoint", "network_name", "network_driver",
    "network_internal", "labels", "argv", "operator_id", "nonce",
    "requested_ttl_seconds", "operator_verified", "issue_authorized",
    "create_authorized", "launch_authorized", "request_hash",
})


@dataclass(frozen=True)
class NetworkRequestCheck:
    matches: bool
    reason: str


def check_network_create_issue_request(
    request: object, *, expected_request_hash: str, expected_commit: str,
    expected_docker_sha256: str, expected_attempt_id: str,
    expected_operator_id: str, expected_network_name: str,
    expected_labels: dict[str, str],
) -> NetworkRequestCheck:
    """Compare candidate data with separately established expected values."""
    if (type(request) is not dict or set(request) != _FIELDS
            or any(type(value) is not str or not _HEX.fullmatch(value)
                   for value in (expected_request_hash, expected_commit,
                                 expected_docker_sha256))
            or any(type(value) is not str or not value
                   for value in (expected_attempt_id, expected_operator_id,
                                 expected_network_name))
            or type(expected_labels) is not dict
            or any(type(key) is not str or type(value) is not str
                   for key, value in expected_labels.items())):
        return NetworkRequestCheck(False, "REQUEST_OR_EXPECTATION_INVALID")
    if (request["schema_id"] != "hermes.agent-local-kilo-network-issue-request/v1"
            or request["action"] != "network_create"
            or request["docker_engine_endpoint"] != _ENDPOINT
            or request["network_driver"] != "bridge"
            or request["network_internal"] is not True):
        return NetworkRequestCheck(False, "NETWORK_SCOPE_MISMATCH")
    for field in ("operator_verified", "issue_authorized",
                  "create_authorized", "launch_authorized"):
        if request[field] is not False:
            return NetworkRequestCheck(False, "AUTHORITY_FLAG_PRESENT")
    for field in ("intent_hash", "candidate_hash", "spec_hash"):
        value = request[field]
        if type(value) is not str or not _HEX.fullmatch(value):
            return NetworkRequestCheck(False, "PLAN_HASH_INVALID")
    if (not _NETWORK.fullmatch(expected_network_name)
            or set(expected_labels) != _LABELS
            or expected_labels["hermes.ea4e.attempt"] != expected_attempt_id
            or expected_labels["hermes.ea4e.candidate_sha256"]
            != request["candidate_hash"]
            or expected_labels["hermes.ea4e.profile"]
            != "FAKE_ONLY_LOCAL_CONTAINER"
            or not _OWNER.fullmatch(
                expected_labels["hermes.ea4e.cleanup_owner"]
            )):
        return NetworkRequestCheck(False, "FAKE_NETWORK_PROFILE_MISMATCH")
    if (request["governing_commit"] != expected_commit
            or request["docker_executable_sha256"] != expected_docker_sha256
            or request["attempt_id"] != expected_attempt_id
            or request["operator_id"] != expected_operator_id
            or request["network_name"] != expected_network_name
            or type(request["nonce"]) is not str or not request["nonce"]
            or type(request["requested_ttl_seconds"]) is not int
            or not 0 < request["requested_ttl_seconds"] <= 300):
        return NetworkRequestCheck(False, "REQUEST_IDENTITY_MISMATCH")
    if request["labels"] != expected_labels:
        return NetworkRequestCheck(False, "NETWORK_LABELS_MISMATCH")
    argv = ["network", "create", "--driver", "bridge", "--internal"]
    for key, value in sorted(expected_labels.items()):
        argv.extend(("--label", f"{key}={value}"))
    argv.append(expected_network_name)
    if request["argv"] != argv:
        return NetworkRequestCheck(False, "NETWORK_ARGV_MISMATCH")
    try:
        payload = {key: value for key, value in request.items()
                   if key != "request_hash"}
        digest = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return NetworkRequestCheck(False, "REQUEST_HASH_INVALID")
    if (type(request["request_hash"]) is not str
            or request["request_hash"] != digest
            or digest != expected_request_hash):
        return NetworkRequestCheck(False, "REQUEST_HASH_MISMATCH")
    return NetworkRequestCheck(True, "REQUEST_BYTES_MATCH_ONLY")
