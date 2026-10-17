"""Native local-pipe token observation, without operator or issuer authority."""

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
    target = tmp_path_factory.mktemp("pipe-client-token") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4ePipeClientTokenCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92lf_pipe_client_token_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, sid):
    return subprocess.run(
        [str(executable), sid], capture_output=True, text=True,
        timeout=10, check=False,
    )


def test_same_process_client_token_observed_without_authority(executable):
    result = check(executable, "SELF")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "MATCH:CLIENT_TOKEN_OBSERVED_ONLY"


def test_wrong_sid_denied(executable):
    result = check(executable, "S-1-5-18")
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:CLIENT_SID_MISMATCH"


@pytest.mark.parametrize("sid", ["", "not-a-sid", "S-1-5-18x"])
def test_invalid_expected_sid_denied(executable, sid):
    result = check(executable, sid)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:EXPECTED_APP_SID_INVALID"
