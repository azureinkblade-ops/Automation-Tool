"""Exercise owner cleanup control flow with inert dependencies only."""

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
OWNER = ROOT / "tools" / "Ea4eDirectory2OneAttemptCandidate.cs"
FIXTURE = (ROOT / "tests" / "hermes_core" / "fixtures"
           / "ea4e92qj_close_fault_injection.cs")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("ea4e92qj-close-fault") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe",
         "/main:Ea4e92qjCloseFaultInjection", f"/out:{target}",
         str(OWNER), str(FIXTURE)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode,observation", [
    ("owned-throw", "DENY:SHAPE"),
    ("accepted-throw", "DENY:INSPECT_AFTER_OBSERVER"),
])
def test_throwing_disposal_reconciles(executable, mode, observation):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "|".join([
        "DENY:POST_ATTEMPT_RECONCILIATION_REQUIRED",
        observation, "DENY:WRAPPER_CLOSE_UNCERTAIN", "1", "1",
        "NO_RETAINED", "volume-observed", "file-observed",
    ])


def test_raw_close_is_marked_uncertain_before_native_call():
    source = OWNER.read_text()
    edge = source.index("if (!transferred)")
    marker = source.index("rawCloseFailed = true;", edge)
    close = source.index("bool closed = CloseHandle(raw);", edge)
    clear = source.index("rawCloseFailed = false;", edge)
    assert marker < close < clear
