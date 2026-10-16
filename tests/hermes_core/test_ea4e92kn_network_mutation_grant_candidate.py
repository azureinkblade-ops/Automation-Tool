"""Pure grant-byte qualification; the probe has no issuer or Docker capability."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
KEYS = (
    "grant_id", "nonce", "store_id", "store_epoch", "attempt_id",
    "request_hash", "predecessor_hash", "source_commit", "operator_sid",
    "docker_executable_sha256", "network_name", "issued_at", "expires_at",
    "artifact_hash",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def candidate(**changes):
    grant = {
        "schema_id": "hermes.docker-network-mutation-grant-candidate/v1",
        "action": "network_create",
        "grant_id": "a" * 64,
        "nonce": "b" * 64,
        "store_id": "c" * 64,
        "store_epoch": 1,
        "attempt_id": "attempt-1",
        "request_hash": "d" * 64,
        "predecessor_hash": "e" * 64,
        "source_commit": "f" * 64,
        "operator_sid": "S-1-5-21-123",
        "docker_executable_sha256": "1" * 64,
        "docker_engine_endpoint": "npipe:////./pipe/dockerDesktopLinuxEngine",
        "network_name": "ea4e-kilo-" + "2" * 32,
        "issued_at": 1_000,
        "expires_at": 1_100,
    }
    grant.update(changes)
    grant["artifact_hash"] = hashlib.sha256(canonical(grant).encode()).hexdigest()
    return grant


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-grant-candidate") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92kn_network_grant_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, tmp_path, grant, *, expected=None, raw=None):
    path = tmp_path / "grant.json"
    path.write_bytes(raw if raw is not None else canonical(grant).encode())
    expected = expected or grant
    return subprocess.run(
        [str(executable), str(path), *(str(expected[key]) for key in KEYS)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_exact_candidate_matches(executable, tmp_path):
    grant = candidate()
    result = check(executable, tmp_path, grant)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:NON_AUTHORIZING_CANDIDATE"


@pytest.mark.parametrize("change", [
    {"action": "gateway_create"},
    {"store_epoch": 0},
    {"expires_at": 1_301},
    {"operator_sid": "not-a-sid"},
    {"network_name": "wrong-network"},
    {"docker_engine_endpoint": "tcp://127.0.0.1:2375"},
])
def test_invalid_scope_denied_even_with_valid_hash(executable, tmp_path, change):
    assert check(executable, tmp_path, candidate(**change)).returncode == 1


@pytest.mark.parametrize("key,value", [
    ("grant_id", "3" * 64),
    ("nonce", "3" * 64),
    ("store_id", "3" * 64),
    ("store_epoch", 2),
    ("attempt_id", "attempt-2"),
    ("request_hash", "3" * 64),
    ("predecessor_hash", "3" * 64),
    ("source_commit", "3" * 64),
    ("operator_sid", "S-1-5-21-456"),
    ("docker_executable_sha256", "3" * 64),
    ("network_name", "ea4e-kilo-" + "3" * 32),
    ("issued_at", 1_001),
    ("expires_at", 1_101),
])
def test_expected_identity_is_independently_bound(executable, tmp_path, key, value):
    grant = candidate()
    altered = candidate(**{key: value})
    assert check(executable, tmp_path, altered, expected=grant).returncode == 1


def test_tampered_hash_and_noncanonical_bytes_denied(executable, tmp_path):
    grant = candidate()
    assert check(executable, tmp_path, grant, raw=(canonical(grant) + " ").encode()).returncode == 1
    tampered = dict(grant, artifact_hash="0" * 64)
    assert check(executable, tmp_path, tampered).returncode == 1
    duplicated = canonical(grant).replace('"action":"network_create",',
                                        '"action":"network_create","action":"network_create",')
    assert check(executable, tmp_path, grant, raw=duplicated.encode()).returncode == 1
