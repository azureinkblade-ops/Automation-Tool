"""Compile retained-handle read candidate; invoke only inert screens."""

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
    target = tmp_path_factory.mktemp("retained-read-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementRetainedReadCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92on_retained_read_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


@pytest.mark.parametrize("attributes,links,size,expected", [
    ("00000080", "1", "1", "CANDIDATE:FILE_SHAPE_ONLY"),
    ("00000080", "1", "1024", "CANDIDATE:FILE_SHAPE_ONLY"),
    ("00000480", "1", "1", "DENY:REPARSE"),
    ("00000010", "1", "1", "DENY:NOT_FILE"),
    ("00000080", "0", "1", "DENY:MULTILINK"),
    ("00000080", "2", "1", "DENY:MULTILINK"),
    ("00000080", "1", "0", "DENY:SIZE"),
    ("00000080", "1", "1025", "DENY:SIZE"),
])
def test_inert_file_shape(executable, attributes, links, size, expected):
    result = call(executable, "screen", attributes, links, size)
    assert result.returncode == 0
    assert result.stdout.strip() == expected


def test_exact_read_limit(executable):
    result = call(executable, "limit")
    assert result.returncode == 0
    assert result.stdout.strip() == "1024"


@pytest.mark.parametrize("args", [
    (), ("read",), ("screen", "80", "1"),
    ("screen", "g", "1", "1"),
])
def test_no_native_read_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
