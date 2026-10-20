"""Read-only ProgramData lookup does not qualify installation or ACLs."""

import os
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
    target = tmp_path_factory.mktemp("ea4e92pd-known-folder") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProgramDataKnownFolderCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pd_known_folder_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_read_only_known_folder_lookup(executable):
    result = subprocess.run(
        [str(executable), "--resolve"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    prefix = "CANDIDATE:KNOWN_FOLDER_PATH_ONLY:"
    assert result.stdout.strip().startswith(prefix)
    path = result.stdout.strip()[len(prefix):]
    assert Path(path).is_dir()
    assert path.lower() == os.environ["PROGRAMDATA"].lower()


def test_source_has_no_installer_or_runtime_route():
    source = (ROOT / "tools" / "Ea4eProgramDataKnownFolderCandidate.cs").read_text()
    assert "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97" in source
    assert "SHGetKnownFolderPath(ref id, 0, IntPtr.Zero" in source
    for forbidden in ("CreateDirectory", "CreateFile", "Process.Start", "docker", "Kilo", "OpenCode"):
        assert forbidden not in source
