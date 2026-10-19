"""Pure issuer-policy byte validation; expected hash is only a test input."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import CSC, ROOT


def policy(**changes):
    values = {
        "schema_id": "hermes.ea4e.protected-issuer-policy/v1",
        "profile": "LOCAL_CONTAINER_PROTECTED_ISSUER",
        "action": "network_create",
        "installation_version": "v1",
        "issuer_path": r"C:\Program Files\Hermes\Issuer\issuer.exe",
        "issuer_sha256": "a" * 64,
        "dependency_manifest_path": r"C:\Program Files\Hermes\Issuer\dependencies.json",
        "dependency_manifest_hash": "b" * 64,
        "policy_path": r"C:\Program Files\Hermes\Issuer\policy.json",
        "operator_sid": "S-1-5-21-123",
        "app_sid": "S-1-5-21-456",
        "governing_commit": "c" * 64,
        "authority_id": "d" * 64,
        "store_path": r"C:\ProgramData\Hermes\issuer.sqlite",
        "anchor_prefix": r"C:\ProgramData\Hermes\issuer.anchor",
        "store_id": "e" * 64,
        "store_epoch": 1,
        "docker_executable_path": r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        "docker_executable_sha256": "f" * 64,
        "docker_engine_endpoint": "npipe:////./pipe/dockerDesktopLinuxEngine",
        "max_ttl_seconds": 300,
        "one_attempt_budget": 1,
    }
    values.update(changes)
    return values


def canonical(values):
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("issuer-policy") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eProtectedIssuerPolicyCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mv_issuer_policy_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, tmp_path, values, *, raw=None, expected_hash=None):
    data = raw if raw is not None else canonical(values).encode()
    path = tmp_path / "policy.json"
    path.write_bytes(data)
    digest = expected_hash if expected_hash is not None else hashlib.sha256(data).hexdigest()
    return subprocess.run(
        [str(executable), str(path), digest],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_canonical_policy_bytes_match(executable, tmp_path):
    result = check(executable, tmp_path, policy())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:PURE_POLICY_BYTES:network_create:1"


def test_external_hash_must_match(executable, tmp_path):
    assert check(executable, tmp_path, policy(), expected_hash="0" * 64).returncode == 1


@pytest.mark.parametrize("change", [
    {"schema_id": "hermes.ea4e.protected-issuer-policy/v2"},
    {"profile": "FAKE_ONLY_LOCAL_CONTAINER"},
    {"action": "container_create"},
    {"operator_sid": "bad"},
    {"app_sid": "bad"},
    {"issuer_sha256": "bad"},
    {"governing_commit": "bad"},
    {"store_id": "bad"},
    {"store_epoch": 0},
    {"max_ttl_seconds": 301},
    {"one_attempt_budget": 2},
    {"docker_engine_endpoint": "tcp://localhost:2375"},
    {"issuer_path": r"C:\Temp\issuer.exe" + ":stream"},
    {"policy_path": r"C:\Program Files\Hermes\..\policy.json"},
    {"dependency_manifest_path": r"C:\Temp\dependencies.json"},
    {"dependency_manifest_path": r"C:\Program Files\Hermes\Issuer\issuer.exe"},
    {"anchor_prefix": r"C:\Temp\issuer.anchor"},
    {"extra_authority": "bad"},
])
def test_invalid_scope_denied_even_with_matching_hash(executable, tmp_path, change):
    assert check(executable, tmp_path, policy(**change)).returncode == 1


def test_missing_noncanonical_and_unicode_bytes_denied(executable, tmp_path):
    values = policy()
    missing = dict(values)
    missing.pop("authority_id")
    assert check(executable, tmp_path, missing).returncode == 1
    assert check(executable, tmp_path, values,
                 raw=(canonical(values) + " ").encode()).returncode == 1
    unicode_policy = policy(installation_version="v1-\u00e9")
    assert check(executable, tmp_path, unicode_policy,
                 raw=json.dumps(unicode_policy, sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False).encode()).returncode == 1
