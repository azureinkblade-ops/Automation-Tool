"""Kernel-observed process handle remains read-only and non-authorizing."""

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
    target = tmp_path_factory.mktemp("pipe-process-lease") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4ePipeClientProcessLeaseCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92na_pipe_process_lease_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(("mode", "expected", "status"), [
    ("OBSERVE", "MATCH:KERNEL_CLIENT_PROCESS_OBSERVED_ONLY", 0),
    ("CALLBACK_DENY", "DENY:CALLBACK_DENIED", 1),
    ("NO_OBSERVER", "DENY:PROCESS_OBSERVER_UNAVAILABLE", 1),
    ("NO_PIPE", "DENY:PIPE_HANDLE_UNAVAILABLE", 1),
])
def test_kernel_client_process_lease_is_read_only(
    executable, mode, expected, status,
):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == status, result.stdout + result.stderr
    assert result.stdout.strip() == expected
