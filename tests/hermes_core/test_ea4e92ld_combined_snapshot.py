"""A single retained handle set observes ACLs and leaf bytes, without authority."""

import hashlib
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
    target = tmp_path_factory.mktemp("combined-snapshot") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedByteSnapshotCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPathAccessCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ld_combined_snapshot_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, path, root, sid="SELF", digest=None):
    digest = digest or hashlib.sha256(b"inert").hexdigest()
    return subprocess.run(
        [str(executable), str(path), str(root), sid, digest],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_app_owned_leaf_denied_even_when_bytes_match(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, tmp_path)
    assert result.returncode == 1
    assert result.stdout.strip() in {
        "DENY:APP_OWNS_OBJECT", "DENY:APP_MUTATION_RIGHTS",
        "DENY:APP_TOKEN_NOT_UNELEVATED",
    }


def test_wrong_app_sid_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, tmp_path, sid="S-1-5-18")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:APP_IDENTITY_MISMATCH"


def test_noncanonical_digest_denied_before_path_observation(executable, tmp_path):
    result = check(executable, tmp_path / "missing.exe", tmp_path, digest="G" * 64)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_HASH_INVALID"


def test_target_outside_protected_root_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, tmp_path / "other")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:PROTECTED_ROOT_UNBOUND"


def test_missing_target_denied(executable, tmp_path):
    result = check(executable, tmp_path / "missing.exe", tmp_path)
    assert result.returncode == 1
    assert result.stdout.strip() != "MATCH:ACL_AND_BYTE_SNAPSHOT_ONLY"
