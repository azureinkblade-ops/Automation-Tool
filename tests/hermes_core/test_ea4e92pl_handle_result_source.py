"""Pure CreateDirectory2 result classification; no native create."""

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
    target = tmp_path_factory.mktemp("ea4e92pl-result") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eDirectory2HandleResultCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pl_handle_result_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("value,expected", [
    ("0", "DENY:NULL_HANDLE"),
    ("-1", "DENY:INVALID_HANDLE_VALUE"),
    ("1", "CANDIDATE:NON_SENTINEL_ONLY"),
    ("12345", "CANDIDATE:NON_SENTINEL_ONLY"),
])
def test_result_screen(executable, value, expected):
    result = subprocess.run(
        [str(executable), value], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == expected


def test_no_native_route():
    source = (ROOT / "tools" / "Ea4eDirectory2HandleResultCandidate.cs").read_text()
    for forbidden in ("DllImport", "CreateDirectory2W", "CreateFile", "CloseHandle"):
        assert forbidden not in source
