"""Read-only held-handle byte snapshots; no mapped-image or issuer authority."""

import hashlib
import os
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
    target = tmp_path_factory.mktemp("protected-byte-snapshot") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedByteSnapshotCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92lc_protected_byte_snapshot_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, path, digest):
    return subprocess.run(
        [str(executable), str(path), digest], capture_output=True,
        text=True, timeout=10, check=False,
    )


def test_matching_bytes_are_only_a_snapshot(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    content = b"inert candidate bytes"
    target.write_bytes(content)
    result = check(executable, target, hashlib.sha256(content).hexdigest())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:BYTE_SNAPSHOT_ONLY"
    assert target.read_bytes() == content


def test_changed_bytes_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"changed")
    result = check(executable, target, hashlib.sha256(b"original").hexdigest())
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:BYTE_HASH_MISMATCH"


def test_empty_file_snapshot(executable, tmp_path):
    target = tmp_path / "empty.exe"
    target.write_bytes(b"")
    result = check(executable, target, hashlib.sha256(b"").hexdigest())
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:BYTE_SNAPSHOT_ONLY"


@pytest.mark.parametrize("digest", ["", "0" * 63, "A" * 64, "g" * 64])
def test_noncanonical_digest_denied(executable, tmp_path, digest):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert")
    result = check(executable, target, digest)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_HASH_INVALID"


def test_missing_file_denied(executable, tmp_path):
    result = check(executable, tmp_path / "missing.exe", "0" * 64)
    assert result.returncode == 1
    assert result.stdout.strip() != "MATCH:BYTE_SNAPSHOT_ONLY"


def test_relative_path_denied(executable):
    result = check(executable, "relative\\candidate.exe", "0" * 64)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:PATH_FORM_DENIED"


def test_hardlinked_file_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    content = b"inert"
    target.write_bytes(content)
    try:
        os.link(target, tmp_path / "alternate.exe")
    except OSError as error:
        pytest.skip(f"Hard links unavailable: {error}")
    result = check(executable, target, hashlib.sha256(content).hexdigest())
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:MULTILINK_DENIED"


def test_symlink_denied_when_supported(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    content = b"inert"
    target.write_bytes(content)
    link = tmp_path / "linked.exe"
    try:
        os.symlink(target, link)
    except OSError as error:
        pytest.skip(f"Symlinks unavailable: {error}")
    result = check(executable, link, hashlib.sha256(content).hexdigest())
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:REPARSE_DENIED"
