"""Compile peer-binding source; exercise only inert identity screens."""

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
    target = tmp_path_factory.mktemp("creator-peer-source") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eCreatorPeerBindingCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92ov_creator_peer_source_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run([str(executable), *args], capture_output=True,
                          text=True, timeout=10, check=False)


@pytest.mark.parametrize("args,expected", [
    (("screen", "1234", "5678", "1234", "5678", "1234"),
     "CANDIDATE:PEER_PROCESS_ONLY"),
    (("screen", "0", "5678", "1234", "5678", "1234"),
     "DENY:PEER_ID_UNAVAILABLE"),
    (("screen", "1234", "0", "1234", "5678", "1234"),
     "DENY:PEER_ID_UNAVAILABLE"),
    (("screen", "1234", "5678", "0", "5678", "1234"),
     "DENY:PEER_ID_UNAVAILABLE"),
    (("screen", "1234", "5678", "1234", "0", "1234"),
     "DENY:PEER_ID_UNAVAILABLE"),
    (("screen", "1234", "5678", "1234", "5678", "0"),
     "DENY:PEER_ID_UNAVAILABLE"),
    (("screen", "1234", "5678", "1235", "5678", "1235"),
     "DENY:PEER_ID_MISMATCH"),
    (("screen", "1234", "5678", "1234", "5679", "1234"),
     "DENY:PEER_ID_MISMATCH"),
    (("screen", "1234", "5678", "1234", "5678", "1235"),
     "DENY:PEER_ID_MISMATCH"),
    (("screen", "1234", "5678", "1234", "5678", "1234", "exited"),
     "DENY:LAUNCH_EXITED_OR_UNKNOWN"),
])
def test_inert_peer_screen(executable, args, expected):
    result = call(executable, *args)
    assert result.returncode == 0
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("args", [(), ("observe",), ("screen", "bad")])
def test_no_native_observe_cli(executable, args):
    result = call(executable, *args)
    assert result.returncode == 2
    assert result.stdout == ""
