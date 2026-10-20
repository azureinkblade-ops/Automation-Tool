"""Static directory descriptor policy, without native directory creation."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-100-200-300-1001"
VALID = ("O:BAG:BAD:P(A;;0x000200a1;;;" + APP + ")"
         "(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92ph-directory") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementFileDescriptorCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ph_directory_descriptor_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def screen(executable, mode, sddl=VALID, sid=APP):
    return subprocess.run(
        [str(executable), mode, sddl, sid], capture_output=True,
        text=True, timeout=10, check=False,
    )


@pytest.mark.parametrize("mode", ["screen", "screen-bytes"])
def test_exact_directory_structure(executable, mode):
    result = screen(executable, mode)
    assert result.returncode == 0
    assert result.stdout.strip() == "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY"


@pytest.mark.parametrize("sddl", [
    VALID.replace("0x000200a1", "0x00020081"),
    VALID.replace("0x000200a1", "0x000200a3"),
    VALID.replace("O:BA", "O:" + APP),
    VALID.replace("D:P", "D:"),
    VALID.replace(";;;SY", ";;;WD"),
    VALID.replace("S:(ML;;NW;;;HI)", "S:(ML;;NW;;;ME)"),
    VALID.replace("S:(ML;;NW;;;HI)", ""),
])
def test_directory_mutations_denied(executable, sddl):
    for mode in ("screen", "screen-bytes"):
        result = screen(executable, mode, sddl)
        assert result.returncode == 0
        assert result.stdout.strip().startswith("DENY:")


def test_no_native_read_or_create_route(executable):
    assert subprocess.run([str(executable), "read"], check=False).returncode == 2
