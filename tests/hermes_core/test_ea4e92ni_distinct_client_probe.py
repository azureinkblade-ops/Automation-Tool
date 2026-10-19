"""Inert separate child process, not a qualified app or receiver."""

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
    target = tmp_path_factory.mktemp("distinct-client-probe") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools/Ea4ePipeChallengeMessageCandidate.cs"),
         str(ROOT / "tools/Ea4ePipeClientProcessLeaseCandidate.cs"),
         str(ROOT / "tests/hermes_core/fixtures/ea4e92ni_distinct_client_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(("mode", "expected"), [
    ("MATCH", "DISTINCT_CLIENT_OBSERVED_ONLY"),
    ("PID_MISMATCH", "CLIENT_IDENTITY_MISMATCH"),
    ("CREATION_MISMATCH", "CLIENT_IDENTITY_MISMATCH"),
])
def test_post_read_observation_of_distinct_inert_client(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == expected
