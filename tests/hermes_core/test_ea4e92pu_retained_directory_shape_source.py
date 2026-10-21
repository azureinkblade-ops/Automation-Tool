"""Inert retained-directory shape screen; native Read is never invoked."""

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
    target = tmp_path_factory.mktemp("ea4e92pu-shape") / "probe.exe"
    sources = (
        ROOT / "tools" / "Ea4eDirectory2RetainedShapeCandidate.cs",
        ROOT / "tools" / "Ea4eAnnouncementFileIdentityCandidate.cs",
        ROOT / "tests" / "hermes_core" / "fixtures"
        / "ea4e92pu_retained_shape_probe.cs",
    )
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode,expected", [
    ("valid", "CANDIDATE:RETAINED_DIRECTORY_SHAPE_ONLY"),
    ("file", "DENY:DIRECTORY_SHAPE"),
    ("reparse", "DENY:DIRECTORY_SHAPE"),
    ("tag-drift", "DENY:DIRECTORY_SHAPE"),
    ("multilink", "DENY:DIRECTORY_SHAPE"),
    ("pipe", "DENY:FILE_TYPE"),
    ("path", "DENY:FINAL_PATH_MISMATCH"),
    ("unc", "DENY:FINAL_PATH_MISMATCH"),
    ("null", "DENY:INVALID_HANDLE"),
])
def test_inert_shape_screen(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


def test_shape_reader_has_no_native_create_or_path_open():
    source = (ROOT / "tools" / "Ea4eDirectory2RetainedShapeCandidate.cs").read_text()
    for forbidden in ("CreateDirectory2W", "CreateFileW", "DeleteFileW"):
        assert forbidden not in source
