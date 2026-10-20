"""Compile the retained file-ID helper and exercise inert paths only."""

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
    target = tmp_path_factory.mktemp("file-identity-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementFileIdentityCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92os_file_identity_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


def test_info_class_is_file_id_info(executable):
    result = call(executable, "--info-class")
    assert result.returncode == 0
    assert result.stdout.strip() == "18"


def test_inert_encoding_matches_v2_contract(executable):
    result = call(executable, "--screen", "1")
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "CANDIDATE:FILE_ID_ONLY",
        "0000000000000001:120000000000000000000000000000ab",
    ]


def test_zero_volume_denied(executable):
    result = call(executable, "--screen", "0")
    assert result.returncode == 0
    assert result.stdout.strip() == "DENY:FILE_ID_SHAPE"


@pytest.mark.parametrize("args", [(), ("--native",), ("--screen",),
                                     ("--screen", "bad")])
def test_no_native_read_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
