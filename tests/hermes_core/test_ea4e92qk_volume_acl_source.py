"""Inert volume ACL flag and P/Invoke declaration checks."""

import subprocess
import sys
import re
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


@pytest.mark.parametrize("mode,expected", [
    ("injected-success", "CANDIDATE:PERSISTENT_ACLS_FLAG_ONLY|8|0"),
    ("injected-unsupported", "DENY:VOLUME_ACLS_UNSUPPORTED|0|0"),
    ("injected-failed-bit", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|5"),
    ("injected-disposed", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|0"),
    ("injected-dll-missing", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|0"),
    ("injected-entry-missing", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|0"),
    ("injected-throw-after-output", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|0"),
    ("injected-failed-zero", "DENY:VOLUME_INFORMATION_UNAVAILABLE|0|0"),
    ("closed-handle", "DENY:RETAINED_HANDLE_UNAVAILABLE|0|0"),
    ("invalid-handle-nonnull", "DENY:RETAINED_HANDLE_UNAVAILABLE|0|0"),
    ("reader-missing", "DENY:VOLUME_READER_MISSING|0|0"),
])
def test_injected_reader_failure_is_not_admission(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


def test_volume_reader_is_unwired():
    source = SOURCE.read_text()
    assert source.count("GetVolumeInformationByHandleW(") == 2
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.cs"], cwd=ROOT,
        capture_output=True, check=True,
    ).stdout
    direct_call = re.compile(
        r"\bEa4eDirectoryVolumeAclCandidate\s*\.\s*Read(?:With)?\s*\("
    )
    callers = [name for name in tracked.decode().split("\0") if name
               and not name.startswith("tests/")
               and name != "tools/Ea4eDirectoryVolumeAclCandidate.cs"
               and direct_call.search((ROOT / name).read_text())]
    assert callers == []
