"""Inert .NET Framework pipe read/cancel observation, not an issuer."""

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
    target = tmp_path_factory.mktemp("pipe-read-probe") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tests/hermes_core/fixtures/ea4e92nf_pipe_read_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(("mode", "expected"), [
    ("COMPLETE", "ONE_BYTE_READ"),
    ("TIMEOUT", "CANCELED_AND_OBSERVED"),
    ("PARTIAL", "PARTIAL_READ_OBSERVED"),
    ("DISCONNECT", "EOF_OBSERVED"),
])
def test_inert_pipe_read_completion(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=9, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == expected
