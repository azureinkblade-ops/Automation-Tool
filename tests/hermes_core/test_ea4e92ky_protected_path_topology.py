"""Read-only Windows handle topology checks; no ACL or issuer authority."""

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
    target = tmp_path_factory.mktemp("protected-path-topology") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ky_protected_path_topology_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, path):
    return subprocess.run(
        [str(executable), str(path)], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_regular_nested_file_matches_topology_only(executable, tmp_path):
    directory = tmp_path / "nested"
    directory.mkdir()
    target = directory / "candidate.exe"
    target.write_bytes(b"inert candidate bytes")
    result = check(executable, target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:TOPOLOGY_ONLY"


@pytest.mark.parametrize("path", [
    "relative\\candidate.exe", "\\\\server\\share\\candidate.exe",
    "C:\\candidate.exe:alternate", "C:/candidate.exe",
    "C:\\windows\\..\\candidate.exe",
])
def test_path_forms_denied(executable, path):
    assert check(executable, path).returncode == 1


def test_missing_target_denied(executable, tmp_path):
    result = check(executable, tmp_path / "missing.exe")
    assert result.returncode == 1
    assert result.stdout.strip() != "MATCH:TOPOLOGY_ONLY"


def test_hardlinked_target_denied(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert candidate bytes")
    alternate = tmp_path / "other-name.exe"
    try:
        os.link(target, alternate)
    except OSError as error:
        pytest.skip(f"Hard links unavailable: {error}")
    result = check(executable, target)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:MULTILINK_DENIED"


def test_symlink_target_denied_when_supported(executable, tmp_path):
    target = tmp_path / "candidate.exe"
    target.write_bytes(b"inert candidate bytes")
    link = tmp_path / "linked.exe"
    try:
        os.symlink(target, link)
    except OSError as error:
        pytest.skip(f"Symlinks unavailable: {error}")
    result = check(executable, link)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:REPARSE_DENIED"


def test_symlink_ancestor_denied_when_supported(executable, tmp_path):
    directory = tmp_path / "real"
    directory.mkdir()
    target = directory / "candidate.exe"
    target.write_bytes(b"inert candidate bytes")
    link = tmp_path / "linked-directory"
    try:
        os.symlink(directory, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks unavailable: {error}")
    result = check(executable, link / target.name)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:REPARSE_DENIED"
