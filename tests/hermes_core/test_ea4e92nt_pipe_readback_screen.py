"""Source-only descriptor-byte screen; native Read must never run here."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-100-200-300-1001"
BASE = (
    "O:BAG:BAD:P(A;;0x00000002;;;" + APP + ")"
    "(A;;GA;;;SY)(A;;GA;;;BA)S:(ML;;NW;;;ME)"
)


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("pipe-readback-screen") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPipeDescriptorScreen.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPipeCreatorCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPipeReadbackCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nt_pipe_readback_screen_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, mode, app=APP, sddl=BASE):
    return subprocess.run(
        [str(executable), mode, app, sddl],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_creator_template_passes_structural_screen(executable):
    result = call(executable, "template")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "CANDIDATE:READBACK_STRUCTURE_ONLY"


@pytest.mark.parametrize("sddl", [
    BASE.replace("O:BA", "O:" + APP),
    BASE.replace("G:BA", "G:SY"),
    BASE.replace("(A;;0x00000002;;;" + APP + ")", ""),
    BASE.replace("(A;;GA;;;BA)", "(A;;GA;;;BA)(A;;GA;;;WD)"),
    BASE.replace("0x00000002", "GW"),
    BASE.replace("S:(ML;;NW;;;ME)", ""),
    BASE.replace("S:(ML;;NW;;;ME)", "S:(ML;;NW;;;HI)"),
    BASE.replace("(A;;GA;;;SY)", "(A;;GA;;;SY)(A;;GA;;;SY)"),
])
def test_wrong_structure_denied(executable, sddl):
    result = call(executable, "sddl", sddl=sddl)
    assert result.stdout.startswith("DENY:"), result.stdout + result.stderr


@pytest.mark.parametrize("sddl,denial", [
    (BASE.replace("S:(ML;;NW;;;ME)", ""),
     "DENY:LABEL_MISSING_OR_UNREVIEWED"),
    (BASE.replace("D:P", "D:"),
     "DENY:DACL_MISSING_OR_UNPROTECTED"),
])
def test_secondary_screen_reason_is_preserved(executable, sddl, denial):
    result = call(executable, "sddl", sddl=sddl)
    assert result.returncode == 0
    assert result.stdout.strip() == denial


def test_foreign_expected_app_denied(executable):
    result = call(executable, "sddl", app="S-1-5-21-100-200-300-1002")
    assert result.stdout.startswith("DENY:"), result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["short", "invalid"])
def test_malformed_bytes_denied(executable, mode):
    result = call(executable, mode)
    assert result.stdout.startswith("DENY:"), result.stdout + result.stderr
