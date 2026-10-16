"""Fail-closed ACL snapshot tests, without issuer or installation authority."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("protected-path-access") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPathAccessCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92la_protected_path_access_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, path, sid="SELF"):
    return subprocess.run(
        [str(executable), str(path), sid], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_expected_app_sid_is_required(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, "")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:APP_IDENTITY_UNBOUND"


def test_wrong_app_sid_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, "S-1-5-18")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:APP_IDENTITY_MISMATCH"


def test_user_writable_path_cannot_match(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target)
    assert result.returncode == 1
    assert result.stdout.strip() in {
        "DENY:APP_OWNS_OBJECT", "DENY:APP_MUTATION_RIGHTS",
        "DENY:APP_TOKEN_NOT_UNELEVATED",
    }


def test_missing_target_denied(executable, tmp_path):
    result = check(executable, tmp_path / "missing.exe")
    assert result.returncode == 1
    assert result.stdout.strip() != "MATCH:ACL_SNAPSHOT_ONLY"
