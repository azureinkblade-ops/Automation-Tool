"""Compile the explicit-rights client candidate, but never invoke native Open."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
CEREMONY = "11111111111111111111111111111111"
RANDOM = "22222222222222222222222222222222"
NAME = rf"\\.\pipe\ea4e-issuer-{CEREMONY}-{RANDOM}"


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("client-open-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPipeAccessProbePolicy.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPipeClientOpenCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92oh_client_open_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("name,expected", [
    (NAME, "CANDIDATE:NAME_SHAPE_ONLY"),
    (r"\\.\pipe\other-" + CEREMONY + "-" + RANDOM,
     "DENY:PIPE_NAME_SHAPE"),
    (NAME + "-extra", "DENY:PIPE_NAME_SHAPE"),
    (NAME.replace(RANDOM, CEREMONY), "DENY:PIPE_NAME_IDENTITY"),
    (NAME.replace(CEREMONY, "0" * 32), "DENY:PIPE_NAME_IDENTITY"),
    (NAME.replace(RANDOM, "G" + RANDOM[1:]), "DENY:PIPE_NAME_IDENTITY"),
    (NAME.upper(), "DENY:PIPE_NAME_SHAPE"),
])
def test_inert_name_shape(executable, name, expected):
    result = subprocess.run(
        [str(executable), "--name-shape", name], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == expected


def test_no_native_cli(executable):
    result = subprocess.run(
        [str(executable), "--open", NAME], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
