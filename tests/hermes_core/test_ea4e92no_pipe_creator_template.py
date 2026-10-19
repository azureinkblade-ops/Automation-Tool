"""Compile and inspect proposed creator template without calling Open()."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
APP = "S-1-5-21-1-2-3-1001"


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("pipe-creator-template") / "template.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedPipeCreatorCandidate.cs"),
         str(ROOT / "tools" / "Ea4eProtectedPipeDescriptorScreen.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92no_pipe_creator_template.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def template(executable, sid):
    result = subprocess.run(
        [str(executable), sid], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def run(executable, *args):
    result = subprocess.run(
        [str(executable), *args], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_template_is_narrow_and_labeled(executable):
    assert template(executable, APP) == (
        "O:BAG:BAD:P(A;;0x00000002;;;" + APP +
        ")(A;;GA;;;SY)(A;;GA;;;BA)S:(ML;;NW;;;ME)"
    )


@pytest.mark.parametrize("sid", ["invalid", "S-1-1-0", "S-1-5-18", "S-1-5-32-544"])
def test_invalid_or_privileged_app_identity_denied(executable, sid):
    assert template(executable, sid) == "DENY:APP_SID_OR_DESCRIPTOR"


def test_open_mode_requests_sacl_readback_access(executable):
    assert run(executable, "MODE") == "41080001"


def test_name_is_ceremony_bound_and_randomized(executable):
    ceremony = "11111111-1111-1111-1111-111111111111"
    random = "22222222-2222-2222-2222-222222222222"
    assert run(executable, "NAME", ceremony, random) == (
        r"\\.\pipe\ea4e-issuer-" + "1" * 32 + "-" + "2" * 32
    )
    assert run(executable, "NAME", ceremony, ceremony) == "DENY:PIPE_NAME"
    assert run(executable, "NAME", "not-a-guid", random) == "DENY:PIPE_NAME"
