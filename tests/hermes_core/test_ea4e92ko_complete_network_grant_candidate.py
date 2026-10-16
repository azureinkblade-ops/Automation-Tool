"""V2 immutable network-grant candidate checks; still no issuer or Docker."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
KEYS = (
    "grant_id", "nonce", "issuer_binary_sha256", "ceremony_id", "store_id",
    "store_epoch", "attempt_id", "authority_id", "request_hash",
    "predecessor_hash", "source_commit", "operator_sid",
    "docker_executable_sha256", "network_name", "issued_at", "expires_at",
    "artifact_hash",
)
LABEL_KEYS = (
    "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
    "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def candidate(**changes):
    grant = {
        "schema_id": "hermes.docker-network-mutation-grant-candidate/v2",
        "action": "network_create",
        "grant_id": "a" * 64,
        "nonce": "b" * 64,
        "issuer_binary_sha256": "3" * 64,
        "ceremony_id": "4" * 64,
        "store_id": "c" * 64,
        "store_epoch": 1,
        "attempt_id": "attempt-1",
        "authority_id": "5" * 64,
        "request_hash": "d" * 64,
        "predecessor_hash": "e" * 64,
        "source_commit": "f" * 64,
        "operator_sid": "S-1-5-21-123",
        "docker_executable_sha256": "1" * 64,
        "docker_engine_endpoint": "npipe:////./pipe/dockerDesktopLinuxEngine",
        "network_name": "ea4e-kilo-" + "2" * 32,
        "network_driver": "bridge",
        "network_internal": True,
        "labels": {
            "hermes.ea4e.attempt": "attempt-1",
            "hermes.ea4e.candidate_sha256": "6" * 64,
            "hermes.ea4e.profile": "FAKE_ONLY_LOCAL_CONTAINER",
            "hermes.ea4e.cleanup_owner": "ea4e-kilo-owner-" + "7" * 32,
        },
        "command_spec_hash": "d" * 64,
        "issued_at": 1_000,
        "expires_at": 1_100,
        "one_attempt_budget": 1,
        "state_at_issue": "ISSUED",
    }
    grant.update(changes)
    grant["artifact_hash"] = hashlib.sha256(canonical(grant).encode()).hexdigest()
    return grant


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("complete-network-grant") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ko_complete_network_grant_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, tmp_path, grant, *, expected=None, labels=None, raw=None):
    path = tmp_path / "complete-grant.json"
    path.write_bytes(raw if raw is not None else canonical(grant).encode())
    expected = expected or grant
    labels = labels or grant["labels"]
    return subprocess.run(
        [str(executable), str(path), *(str(expected[key]) for key in KEYS),
         *(str(labels[key]) for key in LABEL_KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_exact_v2_candidate_matches(executable, tmp_path):
    result = check(executable, tmp_path, candidate())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:NON_AUTHORIZING_COMPLETE_CANDIDATE"


def test_v2_candidate_binds_existing_network_request_fields(executable, tmp_path):
    from tests.hermes_core.test_ea4e92je_agent_local_kilo_daemon_observer import setup
    from tests.hermes_core.test_ea4e92jv_agent_local_kilo_network_issue_request import _build

    source = tmp_path / "network-request"
    source.mkdir()
    start, values, spec, _, _, _ = setup(source)
    try:
        request = _build(values, spec, operator_id="S-1-5-21-123")
    finally:
        start.close()
    grant = candidate(
        attempt_id=request["attempt_id"],
        request_hash=request["request_hash"],
        command_spec_hash=request["request_hash"],
        source_commit=request["governing_commit"],
        operator_sid=request["operator_id"],
        docker_executable_sha256=request["docker_executable_sha256"],
        network_name=request["network_name"],
        labels=request["labels"],
    )
    assert check(executable, tmp_path, grant).returncode == 0


@pytest.mark.parametrize("change", [
    {"schema_id": "hermes.docker-network-mutation-grant-candidate/v1"},
    {"action": "gateway_create"},
    {"docker_engine_endpoint": "tcp://127.0.0.1:2375"},
    {"network_driver": "host"},
    {"network_internal": False},
    {"command_spec_hash": "8" * 64},
    {"one_attempt_budget": 2},
    {"state_at_issue": "CLAIMED"},
    {"store_epoch": 0},
    {"expires_at": 1_301},
])
def test_invalid_scope_denied_with_recomputed_hash(executable, tmp_path, change):
    assert check(executable, tmp_path, candidate(**change)).returncode == 1


@pytest.mark.parametrize("key,value", [
    ("issuer_binary_sha256", "8" * 64),
    ("ceremony_id", "8" * 64),
    ("authority_id", "8" * 64),
    ("store_epoch", 2),
    ("operator_sid", "S-1-5-21-456"),
    ("request_hash", "8" * 64),
    ("network_name", "ea4e-kilo-" + "8" * 32),
])
def test_external_identity_binding(executable, tmp_path, key, value):
    expected = candidate()
    altered = candidate(**{key: value})
    if key == "request_hash":
        altered = candidate(request_hash=value, command_spec_hash=value)
    assert check(executable, tmp_path, altered, expected=expected).returncode == 1


@pytest.mark.parametrize("key,value", [
    ("hermes.ea4e.attempt", "attempt-2"),
    ("hermes.ea4e.candidate_sha256", "8" * 64),
    ("hermes.ea4e.profile", "UNQUALIFIED"),
    ("hermes.ea4e.cleanup_owner", "foreign-owner"),
])
def test_label_binding(executable, tmp_path, key, value):
    baseline = candidate()
    labels = dict(baseline["labels"], **{key: value})
    changed = candidate(labels=labels)
    assert check(executable, tmp_path, changed, labels=baseline["labels"]).returncode == 1


def test_noncanonical_or_extra_field_denied(executable, tmp_path):
    grant = candidate()
    assert check(executable, tmp_path, grant, raw=(canonical(grant) + " ").encode()).returncode == 1
    extra = candidate(extra_authority="not allowed")
    assert check(executable, tmp_path, extra).returncode == 1
