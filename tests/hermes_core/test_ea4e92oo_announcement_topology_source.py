"""Announcement leaf sharing compiles without enabling a native file-open CLI."""

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
    target = tmp_path_factory.mktemp("announcement-topology-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPathTopologyCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92oo_announcement_topology_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


def test_exact_announcement_share_mask(executable):
    result = call(executable, "share")
    assert result.returncode == 0
    assert result.stdout.strip() == "00000003"


def test_missing_observer_denied_before_open(executable):
    result = call(executable, "missing-observer")
    assert result.returncode == 0
    assert result.stdout.strip() == "ANNOUNCEMENT_OBSERVER_REQUIRED"


@pytest.mark.parametrize("path", [
    r"relative\record.json", r"\\server\share\record.json",
    r"C:\record.json:stream", "C:/record.json",
])
def test_bad_path_rejected_before_native_open(executable, path):
    result = call(executable, "invalid-form", path)
    assert result.returncode == 0
    assert result.stdout.strip() == "PATH_FORM_DENIED"


@pytest.mark.parametrize("args", [(), ("open",), ("read", r"C:\x")])
def test_no_native_open_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
