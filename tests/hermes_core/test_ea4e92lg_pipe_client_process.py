"""Read-only pipe client/process-handle binding probe."""

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
    target = tmp_path_factory.mktemp("pipe-client-process") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4ePipeClientProcessCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92lg_pipe_client_process_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("CURRENT", "MATCH:PROCESS_OBJECT_OBSERVED_ONLY"),
     ("NULL", "DENY:EXPECTED_PROCESS_HANDLE_INVALID"),
     ("PSEUDO", "DENY:EXPECTED_PROCESS_HANDLE_INVALID"),
     ("THREAD", "DENY:EXPECTED_PROCESS_HANDLE_INVALID")],
)
def test_pipe_client_matches_only_retained_process_handle(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == (0 if mode == "CURRENT" else 1)
    assert result.stdout.strip() == expected


def test_live_other_process_handle_denied(executable):
    result = subprocess.run(
        [str(executable), "OTHER", str(os.getpid())],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.strip() == "DENY:CLIENT_PROCESS_MISMATCH"
