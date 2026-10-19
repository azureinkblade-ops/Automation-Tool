"""Non-live native operator-token witness; no issuer or Docker mutation."""

import subprocess
import sys
from pathlib import Path

import pytest

from tools.hermes_core.agent_local_docker_operator_token import (
    _read_current_windows_token,
)


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("issuer-token-witness") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedIssuerToken.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mo_issuer_token_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run(
        [str(executable), *args], capture_output=True,
        text=True, timeout=10, check=False,
    )


@pytest.mark.parametrize("expected,observed,elevated,reason", [
    ("S-1-5-21-123-456", "S-1-5-21-123-456", "true", "MATCH_ELEVATED_TOKEN"),
    ("S-1-5-21-123-456", "S-1-5-21-123-456", "false", "TOKEN_NOT_ELEVATED"),
    ("S-1-5-21-123-456", "S-1-5-21-123-789", "true", "TOKEN_SID_MISMATCH"),
    ("invalid", "S-1-5-21-123-456", "true", "EXPECTED_SID_INVALID"),
    ("S-1-5-21-123-456", "invalid", "true", "TOKEN_OBSERVATION_INVALID"),
])
def test_pure_comparison(executable, expected, observed, elevated, reason):
    result = call(executable, "fake", expected, observed, elevated)
    assert result.stdout.strip() == reason
    assert (result.returncode == 0) == (reason == "MATCH_ELEVATED_TOKEN")


def test_current_token_is_observed_without_uac(executable):
    sid, elevated = _read_current_windows_token()
    result = call(executable, "current", sid)
    assert result.stdout.strip() == (
        "MATCH_ELEVATED_TOKEN" if elevated else "TOKEN_NOT_ELEVATED"
    )


def test_current_token_denies_wrong_sid(executable):
    result = call(executable, "current", "S-1-5-21-999999999-999999999-999999999-9999")
    assert result.stdout.strip() == "TOKEN_SID_MISMATCH"
    assert result.returncode == 1
