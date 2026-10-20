"""Compile file-descriptor candidate and exercise static SDDL only."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-100-200-300-1001"
VALID = ("O:BAG:BAD:P(A;;0x00020081;;;" + APP + ")"
         "(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("file-descriptor-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementFileDescriptorCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92oy_file_descriptor_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


def test_exact_static_candidate(executable):
    result = call(executable, "screen", VALID, APP)
    assert result.returncode == 0
    assert result.stdout.strip() == "CANDIDATE:FILE_DESCRIPTOR_STRUCTURE_ONLY"
    raw_result = call(executable, "screen-bytes", VALID, APP)
    assert raw_result.returncode == 0
    assert raw_result.stdout.strip() == "CANDIDATE:FILE_DESCRIPTOR_STRUCTURE_ONLY"


def test_label_requested_without_native_read(executable):
    result = call(executable, "flags")
    assert result.returncode == 0
    assert result.stdout.strip() == "0000001f"


def test_binary_descriptor_trailing_byte_denied(executable):
    result = call(executable, "screen-bytes-extra", VALID, APP)
    assert result.returncode == 0
    assert result.stdout.strip() == "DENY:DESCRIPTOR_TRAILING_BYTES"


@pytest.mark.parametrize("sddl", [
    VALID.replace("O:BA", "O:" + APP),
    VALID.replace("D:P", "D:"),
    VALID.replace("0x00020081", "0x00020083"),
    VALID.replace("0x001f01ff;;;BA", "0x00020081;;;BA"),
    VALID.replace(";;;SY", ";;;WD"),
    VALID.replace("S:(ML;;NW;;;HI)", "S:(ML;;NW;;;ME)"),
    VALID.replace("S:(ML;;NW;;;HI)", ""),
    VALID.replace("S:(ML;;NW;;;HI)", "S:(ML;;NR;;;HI)"),
    VALID + "(A;;GA;;;WD)",
])
def test_mutated_static_descriptor_denied(executable, sddl):
    result = call(executable, "screen", sddl, APP)
    assert result.returncode == 0
    assert result.stdout.strip().startswith("DENY:")
    raw_result = call(executable, "screen-bytes", sddl, APP)
    assert raw_result.returncode == 0
    assert raw_result.stdout.strip().startswith("DENY:")


@pytest.mark.parametrize("args", [(), ("read",), ("screen",),
                                     ("screen", VALID, APP, "extra")])
def test_no_native_read_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
