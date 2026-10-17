"""Read-only current and linked token preflight, without UAC or launch."""

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
    target = tmp_path_factory.mktemp("token-pair-preflight") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eTokenPairPreflight.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_current_token_observed_without_elevation(executable):
    result = subprocess.run(
        [str(executable), "SELF"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert re.fullmatch(r"CURRENT_ELEVATION_TYPE=[123]", lines[0])
    assert re.fullmatch(r"CURRENT_INTEGRITY_SID=S-1-16-\d+", lines[1])
    assert lines[2] in {"LINKED_TOKEN=UNAVAILABLE", "LINKED_TOKEN=OBSERVED"}
    if lines[2] == "LINKED_TOKEN=OBSERVED":
        assert re.fullmatch(r"LINKED_ELEVATION_TYPE=[123]", lines[3])
        assert re.fullmatch(r"LINKED_INTEGRITY_SID=S-1-16-\d+", lines[4])
        assert len(lines) == 5
    else:
        assert len(lines) == 3


def test_arguments_cannot_request_elevation_or_other_process(executable):
    for args in ([], ["ELEVATE"], ["SELF", "1234"]):
        result = subprocess.run(
            [str(executable), *args], capture_output=True, text=True,
            timeout=10, check=False,
        )
        assert result.returncode == 2
        assert result.stdout == ""
