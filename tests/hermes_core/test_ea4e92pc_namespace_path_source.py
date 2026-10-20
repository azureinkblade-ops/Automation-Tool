"""The 92PC comparator never proves installation, topology, or ACLs."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
KNOWN = r"C:\ProgramData"
MANIFEST = r"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1"


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92pc-namespace") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementNamespacePathCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pc_namespace_path_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def check(executable, known=KNOWN, manifest=MANIFEST):
    return subprocess.run(
        [str(executable), known, manifest], capture_output=True,
        text=True, timeout=10, check=False,
    )


def test_exact_values_only(executable):
    result = check(executable)
    assert result.returncode == 0
    assert result.stdout.strip() == "CANDIDATE:PATH_VALUES_ONLY:" + MANIFEST


@pytest.mark.parametrize("known,manifest,denial", [
    (r"C:\Users\David\AppData\Local", MANIFEST, "MANIFEST_MISMATCH"),
    (r"C:\ProgramData\..\Temp", MANIFEST, "KNOWN_FOLDER_FORM"),
    (r"\\server\share", MANIFEST, "KNOWN_FOLDER_FORM"),
    (r"C:\ProgramData", r"C:\Temp\Hermes\EA4E\IssuerAnnouncements\v1", "MANIFEST_MISMATCH"),
    (KNOWN, MANIFEST + r"\..\v1", "MANIFEST_FORM"),
    (KNOWN, MANIFEST + ":stream", "MANIFEST_FORM"),
    (KNOWN, MANIFEST.replace("\\", "/"), "MANIFEST_FORM"),
    (KNOWN, MANIFEST + "\\", "MANIFEST_FORM"),
])
def test_denials(executable, known, manifest, denial):
    result = check(executable, known, manifest)
    assert result.returncode == 1
    assert result.stdout.strip() == "DENY:" + denial


def test_source_has_no_creation_or_runtime_route():
    source = (ROOT / "tools" / "Ea4eAnnouncementNamespacePathCandidate.cs").read_text()
    for forbidden in ("CreateDirectory", "CreateFile", "Process.Start", "docker", "Kilo", "OpenCode"):
        assert forbidden not in source
