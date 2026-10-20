"""Fake-only first-child sequencing; no directory is created."""

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
    target = tmp_path_factory.mktemp("ea4e92pj-fake") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eDirectoryFirstChildCandidate.cs"),
         str(ROOT / "tools" / "Ea4eDirectoryInstallPlanCandidate.cs"),
         str(ROOT / "tools" / "Ea4eAnnouncementNamespacePathCandidate.cs"),
         str(ROOT / "tools" / "Ea4eAnnouncementFileDescriptorCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92pj_first_child_fake_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, mode):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.splitlines()


@pytest.mark.parametrize("mode,expected", [
    ("pass", ["CANDIDATE:FIRST_CHILD_FAKE_ONLY", "1:1:1:True:True"]),
    ("parent", ["DENY:PARENT_PARENT_MISMATCH", "1:0:0:False:False"]),
    ("collision", ["DENY:CREATE_ALREADY_EXISTS", "1:1:0:True:True"]),
    ("missing-handle", ["DENY:CREATE_HANDLE_MISSING", "1:1:0:True:False"]),
    ("readback", ["DENY:CREATED_DESCRIPTOR_MISMATCH", "1:1:1:True:True"]),
    ("throw-parent", ["DENY:PORT_UNCERTAIN", "1:0:0:False:False"]),
    ("throw-create", ["DENY:PORT_UNCERTAIN", "1:1:0:True:True"]),
    ("throw-screen", ["DENY:PORT_UNCERTAIN", "1:1:1:True:True"]),
    ("throw-dispose", ["DENY:PORT_UNCERTAIN", "1:1:1:True:True"]),
])
def test_fake_sequence(executable, mode, expected):
    assert call(executable, mode) == expected


@pytest.mark.parametrize("mode,expected", [
    ("retain-pass", ["CANDIDATE:FIRST_CHILD_FAKE_ONLY", "1:1:1:True:False", "True", "True"]),
    ("retain-collision", ["DENY:CREATE_ALREADY_EXISTS", "1:1:0:True:True", "False", "True"]),
    ("retain-readback", ["DENY:CREATED_DESCRIPTOR_MISMATCH", "1:1:1:True:True", "False", "True"]),
    ("retain-throw-screen", ["DENY:PORT_UNCERTAIN", "1:1:1:True:True", "False", "True"]),
])
def test_handle_transfers_only_after_successful_screen(executable, mode, expected):
    assert call(executable, mode) == expected


def test_source_has_no_native_install_route():
    source = (ROOT / "tools" / "Ea4eDirectoryFirstChildCandidate.cs").read_text()
    for forbidden in ("DllImport", "CreateDirectory2W", "CreateFile", "DeleteFile"):
        assert forbidden not in source
