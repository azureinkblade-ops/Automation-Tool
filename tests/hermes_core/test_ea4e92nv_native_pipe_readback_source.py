"""Compile the native readback fixture, but exercise only its inert CLI path."""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("native-readback-source") / "probe.exe"
    sources = [
        "Ea4eProtectedIssuerToken.cs",
        "Ea4eProtectedPipeDescriptorScreen.cs",
        "Ea4eProtectedPipeCreatorCandidate.cs",
        "Ea4eProtectedPipeReadbackCandidate.cs",
    ]
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(ROOT / "tools" / name) for name in sources),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nv_native_pipe_readback_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_inert_description(executable):
    result = subprocess.run(
        [str(executable), "--describe"], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "SOURCE_ONLY:ONE_PIPE_READBACK_NO_CLIENT"


@pytest.mark.parametrize("args", [[], ["--native-readback"], ["--unknown"]])
def test_incomplete_cli_denied_without_native_call(executable, args):
    result = subprocess.run(
        [str(executable), *args], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("ceremony,offset,denial", [
    ("not-a-guid", 1, "DENY:INPUT"),
    ("00000000-0000-0000-0000-000000000000", 1, "DENY:INPUT"),
    ("11111111-1111-1111-1111-111111111111", -1, "DENY:DEADLINE"),
    ("11111111-1111-1111-1111-111111111111", 5, "DENY:DEADLINE"),
])
def test_preflight_denies_without_native_call(executable, ceremony,
                                               offset, denial):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=offset))
    result = subprocess.run(
        [str(executable), "--native-readback", "S-1-5-21-100-200-300-1001",
         "S-1-5-21-100-200-300-1002", ceremony,
         deadline.strftime("%Y-%m-%dT%H:%M:%SZ")],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 1
    assert result.stdout.strip() == denial
