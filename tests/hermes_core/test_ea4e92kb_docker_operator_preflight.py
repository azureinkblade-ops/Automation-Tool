"""Compile and exercise the non-authorizing Windows operator preflight."""

import subprocess
import sys
from pathlib import Path

import pytest

from tools.hermes_core.agent_local_docker_operator_token import (
    _read_current_windows_token,
)


SOURCE = Path(__file__).resolve().parents[2] / "tools" / "ea4e_docker_operator_preflight.cs"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def candidate(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("operator-preflight") / "preflight.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}", str(SOURCE)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def _run(candidate, *args):
    return subprocess.run(
        [str(candidate), *args], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_current_token_requires_both_sid_and_elevation(candidate):
    sid, elevated = _read_current_windows_token()
    result = _run(candidate, sid)
    if elevated:
        assert result.returncode == 0
        assert result.stdout.strip() == "MATCH:EXPECTED_ELEVATED_TOKEN_OBSERVED"
    else:
        assert result.returncode == 1
        assert result.stdout.strip() == "DENY:OPERATOR_TOKEN_NOT_ELEVATED"


def test_wrong_sid_denied(candidate):
    result = _run(candidate, "S-1-5-21-0-0-0-9999")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:OPERATOR_SID_MISMATCH"


@pytest.mark.parametrize("args", [(), ("invalid",), ("S-1-5",),
                                  ("S-1-5-21-1-2-3", "extra")])
def test_malformed_arguments_denied(candidate, args):
    result = _run(candidate, *args)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_OPERATOR_SID_INVALID"
