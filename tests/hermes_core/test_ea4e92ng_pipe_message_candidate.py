"""One-message bounded byte capture is not a client-identity assertion."""

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
    target = tmp_path_factory.mktemp("pipe-message-probe") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools/Ea4ePipeChallengeMessageCandidate.cs"),
         str(ROOT / "tests/hermes_core/fixtures/ea4e92ng_pipe_message_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize(("mode", "expected"), [
    ("VALID", "BYTES_ONLY"),
    ("OVERSIZE", "FRAME_SIZE_OR_BOUNDARY_INVALID"),
    ("TIMEOUT", "READ_DEADLINE_EXCEEDED"),
    ("DISCONNECT", "CLIENT_DISCONNECTED"),
])
def test_one_message_is_bounded(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=9, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == expected
