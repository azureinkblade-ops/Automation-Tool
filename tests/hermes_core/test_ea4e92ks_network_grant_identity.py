"""Structural v2 identity extraction; independent authority is still required."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    candidate, canonical,
)


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-grant-identity") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         "/r:System.Web.Extensions.dll",
         str(ROOT / "tools" / "Ea4eNetworkMutationGrantCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ks_network_grant_identity_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, tmp_path, raw):
    path = tmp_path / "grant.json"
    path.write_bytes(raw)
    return subprocess.run(
        [str(executable), str(path)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_extracts_only_checked_identity(executable, tmp_path):
    grant = candidate()
    result = check(executable, tmp_path, canonical(grant).encode())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "|".join((
        grant["grant_id"], grant["nonce"], grant["attempt_id"],
        grant["action"], grant["network_name"],
    ))


@pytest.mark.parametrize("change", [
    {"network_internal": False},
    {"one_attempt_budget": 2},
    {"schema_id": "hermes.docker-network-mutation-grant-candidate/v1"},
    {"request_hash": "8" * 64},
    {"nonce": "NOT-A-NONCE"},
])
def test_rejects_invalid_or_inconsistent_artifact(executable, tmp_path, change):
    grant = candidate(**change)
    result = check(executable, tmp_path, canonical(grant).encode())
    assert result.returncode == 1


def test_rejects_noncanonical_and_tampered_bytes(executable, tmp_path):
    grant = candidate()
    raw = canonical(grant).encode()
    assert check(executable, tmp_path, json.dumps(grant).encode()).returncode == 1
    assert check(executable, tmp_path, raw.replace(b'"nonce":"', b'"nonce":"0', 1)).returncode == 1
    assert check(executable, tmp_path, raw + b" ").returncode == 1


def test_rejects_duplicate_keys(executable, tmp_path):
    grant = candidate()
    raw = canonical(grant).encode()
    raw = raw.replace(b'"action":"network_create",',
                      b'"action":"network_create","action":"network_create",', 1)
    assert check(executable, tmp_path, raw).returncode == 1
