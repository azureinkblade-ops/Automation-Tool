"""Inert access-mask and error classification; no native pipe calls."""

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
    target = tmp_path_factory.mktemp("pipe-access-policy") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPipeAccessProbePolicy.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92og_pipe_access_policy_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run(
        [str(executable), *args], capture_output=True, text=True,
        timeout=10, check=False,
    )


@pytest.mark.parametrize("attempt,mask", [
    ("SPECIFIC_WRITE", "00000002"),
    ("GENERIC_WRITE", "40000000"),
    ("WRITE_DAC", "00040000"),
    ("WRITE_OWNER", "00080000"),
])
def test_exact_requested_access(executable, attempt, mask):
    result = call(executable, "mask", attempt)
    assert result.returncode == 0
    assert result.stdout.strip() == mask


@pytest.mark.parametrize("attempt,opened,error,expected", [
    ("SPECIFIC_WRITE", "1", "0", "CANDIDATE:WRITE_HANDLE_ONLY"),
    ("SPECIFIC_WRITE", "0", "5", "DENY:SPECIFIC_WRITE_ACCESS"),
    ("GENERIC_WRITE", "0", "5", "OBSERVED:ACCESS_DENIED_ONLY"),
    ("WRITE_DAC", "0", "5", "OBSERVED:ACCESS_DENIED_ONLY"),
    ("WRITE_OWNER", "0", "5", "OBSERVED:ACCESS_DENIED_ONLY"),
    ("GENERIC_WRITE", "1", "0", "DENY:UNEXPECTED_OPEN"),
    ("WRITE_DAC", "1", "0", "DENY:UNEXPECTED_OPEN"),
    ("WRITE_OWNER", "1", "0", "DENY:UNEXPECTED_OPEN"),
    ("GENERIC_WRITE", "0", "231", "DENY:PIPE_BUSY_NOT_ACL"),
    ("WRITE_DAC", "0", "2", "DENY:PIPE_MISSING_NOT_ACL"),
    ("WRITE_OWNER", "0", "3", "DENY:PIPE_MISSING_NOT_ACL"),
    ("SPECIFIC_WRITE", "0", "87", "DENY:OTHER_OPEN_ERROR"),
    ("BAD", "0", "5", "DENY:UNKNOWN_ATTEMPT"),
])
def test_inert_classification(executable, attempt, opened, error, expected):
    result = call(executable, "classify", attempt, opened, error)
    assert result.returncode == 0
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("args", [
    (), ("mask",), ("classify", "WRITE_DAC", "maybe", "5"),
    ("classify", "WRITE_DAC", "0", "-1"),
])
def test_malformed_cli_never_calls_native(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
