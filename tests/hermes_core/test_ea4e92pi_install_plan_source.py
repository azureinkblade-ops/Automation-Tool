"""A value-only installer plan cannot create or attest a directory."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-100-200-300-1001"
KNOWN = r"C:\ProgramData"
MANIFEST = r"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements\v1"


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92pi-plan") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eDirectoryInstallPlanCandidate.cs"),
         str(ROOT / "tools" / "Ea4eAnnouncementNamespacePathCandidate.cs"),
         str(ROOT / "tools" / "Ea4eAnnouncementFileDescriptorCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pi_install_plan_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, known=KNOWN, manifest=MANIFEST, app=APP):
    return subprocess.run(
        [str(executable), known, manifest, app], capture_output=True,
        text=True, timeout=10, check=False,
    )


def test_exact_plan_values_only(executable):
    result = call(executable)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "CANDIDATE:PLAN_VALUES_ONLY", "1", "3", "012200a1",
        r"C:\ProgramData\Hermes", r"C:\ProgramData\Hermes\EA4E",
        r"C:\ProgramData\Hermes\EA4E\IssuerAnnouncements", MANIFEST,
        "O:BAG:BAD:P(A;;0x000200a1;;;" + APP + ")"
        "(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)",
    ]


@pytest.mark.parametrize("known,manifest,app", [
    (r"C:\Users\David\AppData\Local", MANIFEST, APP),
    (KNOWN, r"C:\Temp\Hermes\EA4E\IssuerAnnouncements\v1", APP),
    (KNOWN, MANIFEST, "S-1-5-32-545"),
    (KNOWN, MANIFEST, "not-a-sid"),
])
def test_bad_plan_denied(executable, known, manifest, app):
    result = call(executable, known, manifest, app)
    assert result.returncode == 1
    assert result.stdout.strip().startswith("DENY:")


def test_no_native_create_route():
    source = (ROOT / "tools" / "Ea4eDirectoryInstallPlanCandidate.cs").read_text()
    for forbidden in ("DllImport", "CreateDirectory", "CreateFile", "Process.Start"):
        assert forbidden not in source
