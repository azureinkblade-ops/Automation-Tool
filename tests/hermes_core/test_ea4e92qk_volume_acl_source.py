"""Inert volume ACL flag and P/Invoke declaration checks."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SOURCE = ROOT / "tools" / "Ea4eDirectoryVolumeAclCandidate.cs"
FIXTURE = (ROOT / "tests" / "hermes_core" / "fixtures"
           / "ea4e92qk_volume_acl_screen.cs")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92qk-volume-acl") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe",
         "/main:Ea4e92qkVolumeAclScreen", f"/out:{target}",
         str(SOURCE), str(FIXTURE)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode,expected", [
    ("supported", "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY"),
    ("supported-plus", "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY"),
    ("unsupported", "DENY:VOLUME_ACLS_UNSUPPORTED"),
    ("failed-with-bit", "DENY:VOLUME_INFORMATION_UNAVAILABLE"),
    ("invalid-handle", "DENY:RETAINED_HANDLE_UNAVAILABLE"),
    ("abi", "CANDIDATE:DECLARATION_ONLY"),
])
def test_inert_volume_acl_screen(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


def test_volume_reader_is_unwired():
    source = SOURCE.read_text()
    assert source.count("GetVolumeInformationByHandleW(") == 2
    callers = [path.name for path in (ROOT / "tools").glob("Ea4e*.cs")
               if path.name != SOURCE.name and
               "Ea4eDirectoryVolumeAclCandidate.Read(" in path.read_text()]
    assert callers == []
