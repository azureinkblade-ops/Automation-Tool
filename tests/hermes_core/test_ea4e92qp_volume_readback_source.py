"""Compile the parent-volume probe but exercise only pre-native CLI paths."""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
FIXTURE = (ROOT / "tests" / "hermes_core" / "fixtures"
           / "ea4e92qp_volume_readback_probe.cs")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92qp-volume") / "probe.exe"
    sources = [
        ROOT / "tools" / "Ea4eProgramDataKnownFolderCandidate.cs",
        ROOT / "tools" / "Ea4eDirectoryVolumeAclCandidate.cs",
        FIXTURE,
    ]
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_inert_description(executable):
    result = subprocess.run(
        [str(executable), "--describe"], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "SOURCE_ONLY:PROGRAMDATA_VOLUME_FLAG_PROBE"


@pytest.mark.parametrize("args", [[], ["--native-volume"], ["--unknown"]])
def test_incomplete_cli_has_no_native_path(executable, args):
    result = subprocess.run(
        [str(executable), *args], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("ceremony,offset,denial,exit_code", [
    ("not-a-guid", 1, "DENY:INPUT", 10),
    ("00000000-0000-0000-0000-000000000000", 1, "DENY:INPUT", 10),
    ("11111111-1111-1111-1111-111111111111", -1, "DENY:DEADLINE", 11),
    ("11111111-1111-1111-1111-111111111111", 5, "DENY:DEADLINE", 11),
])
def test_preflight_denies_before_native_call(executable, ceremony, offset,
                                               denial, exit_code):
    deadline = datetime.now(timezone.utc) + timedelta(minutes=offset)
    result = subprocess.run(
        [str(executable), "--native-volume", r"C:\ProgramData",
         "S-1-5-21-100-200-300-1001", ceremony,
         deadline.strftime("%Y-%m-%dT%H:%M:%SZ")],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == exit_code
    assert result.stdout.strip() == denial


def test_native_entry_is_unwired_source_only():
    source = FIXTURE.read_text()
    assert source.count("Ea4eDirectoryVolumeAclCandidate.Read(") == 1
    assert "FILE_WRITE_DATA" not in source
    assert "CreateDirectory2W" not in source
