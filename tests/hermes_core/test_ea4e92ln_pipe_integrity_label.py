"""Read-only mandatory-label API candidate on a same-token fixture."""

import re
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
    target = tmp_path_factory.mktemp("pipe-integrity-label") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4ePipeIntegrityLabelCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ln_pipe_integrity_label_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_invalid_handle_denied(executable):
    result = subprocess.run(
        [str(executable), "INVALID"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "DENY:PIPE_HANDLE_UNAVAILABLE"


def test_fixture_label_observed_without_authority(executable):
    result = subprocess.run(
        [str(executable), "FIXTURE"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = result.stdout.strip()
    assert re.fullmatch(r"OBSERVED:(UNLABELED|S-1-16-\d+:[0-9A-F]{8})", observed), (
        result.stdout + result.stderr
    )
    if observed != "OBSERVED:UNLABELED":
        assert int(observed.rsplit(":", 1)[1], 16) & 1
