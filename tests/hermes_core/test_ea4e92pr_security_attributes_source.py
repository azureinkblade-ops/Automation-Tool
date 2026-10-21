"""Inert SECURITY_ATTRIBUTES observation; no native directory creation."""

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
    target = tmp_path_factory.mktemp("ea4e92pr-attributes") / "probe.exe"
    sources = (
        ROOT / "tools" / "Ea4eDirectory2SecurityAttributesCandidate.cs",
        ROOT / "tools" / "Ea4eAnnouncementFileDescriptorCandidate.cs",
        ROOT / "tests" / "hermes_core" / "fixtures"
        / "ea4e92pr_security_attributes_probe.cs",
    )
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode,expected", [
    ("valid", "CANDIDATE:ATTRIBUTES_OBSERVED_ONLY"),
    ("invalid", "DENY:DESCRIPTOR"),
    ("missing", "DENY:OBSERVER_MISSING"),
])
def test_inert_attribute_marshalling(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


def test_native_struct_layout_offsets(executable):
    result = subprocess.run(
        [str(executable), "layout"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() in (
        ["4:0:4:8:12:True"], ["8:0:8:16:24:True"],
    )


def test_candidate_has_no_native_create_call():
    source = (ROOT / "tools" / "Ea4eDirectory2SecurityAttributesCandidate.cs").read_text()
    for forbidden in ("DllImport", "CreateDirectory2W", "CreateFile", "DeleteFile"):
        assert forbidden not in source
