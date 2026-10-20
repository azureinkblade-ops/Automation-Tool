"""Compile and exercise masks only; no announcement file is opened."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
EXPECTED = ("01020002", "00000001", "00020081", "00000003")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("announcement-share") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eAnnouncementSharePolicyCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92om_announcement_share_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


def test_exact_masks(executable):
    result = call(executable, "masks")
    assert result.returncode == 0
    assert tuple(result.stdout.strip().split(",")) == EXPECTED
    assert call(executable, "screen", *EXPECTED).stdout.strip() == \
        "CANDIDATE:SHARE_MASKS_ONLY"


@pytest.mark.parametrize("index,replacement", [
    (0, "00020002"), (0, "00000002"),
    (1, "00000000"), (1, "00000003"),
    (2, "00000001"), (2, "40020081"),
    (3, "00000001"), (3, "00000007"),
])
def test_mutated_masks_deny(executable, index, replacement):
    values = list(EXPECTED)
    values[index] = replacement
    result = call(executable, "screen", *values)
    assert result.returncode == 0
    assert result.stdout.strip() == "DENY:ANNOUNCEMENT_SHARE_POLICY"


@pytest.mark.parametrize("args", [(), ("open",), ("screen", "bad")])
def test_no_native_open_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
