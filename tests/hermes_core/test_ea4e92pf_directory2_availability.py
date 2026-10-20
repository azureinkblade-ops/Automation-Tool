"""Export presence is not a directory creation or ACL proof."""

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
    target = tmp_path_factory.mktemp("ea4e92pf-export") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eDirectory2AvailabilityCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pf_directory2_export_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_export_present_without_creating_directory(executable):
    result = subprocess.run(
        [str(executable), "--export"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "CANDIDATE:EXPORT_PRESENT_ONLY"


def test_no_creation_import_or_call():
    source = (ROOT / "tools" / "Ea4eDirectory2AvailabilityCandidate.cs").read_text()
    assert "GetProcAddress(module, \"CreateDirectory2W\")" in source
    assert 'EntryPoint = "CreateDirectory2W"' not in source
    assert "CreateFile" not in source
