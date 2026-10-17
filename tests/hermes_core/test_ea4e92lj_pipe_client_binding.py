"""Combined local-pipe process and token observation, without issuer authority."""

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
    target = tmp_path_factory.mktemp("pipe-client-binding") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4ePipeClientBindingCandidate.cs"),
         str(ROOT / "tools" / "Ea4ePipeClientProcessCandidate.cs"),
         str(ROOT / "tools" / "Ea4ePipeClientTokenCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92lj_pipe_client_binding_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("MATCH", "MATCH:PIPE_CLIENT_OBSERVED_ONLY"),
     ("WRONG_SID", "DENY:CLIENT_SID_MISMATCH"),
     ("BAD_SID", "DENY:EXPECTED_APP_SID_INVALID"),
     ("WRONG_PROCESS", "DENY:CLIENT_PROCESS_MISMATCH")],
)
def test_combined_pipe_binding(executable, mode, expected):
    args = [str(executable), mode]
    if mode == "WRONG_PROCESS":
        args.append(str(os.getpid()))
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == (0 if mode == "MATCH" else 1), (
        result.stdout + result.stderr
    )
    assert result.stdout.strip() == expected
