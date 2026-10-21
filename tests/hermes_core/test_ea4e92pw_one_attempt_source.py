"""Compile the owner but exercise only its pre-call policy screen."""

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
    target = tmp_path_factory.mktemp("ea4e92pw-owner") / "probe.exe"
    sources = sorted((ROOT / "tools").glob("Ea4e*.cs"))
    sources.append(ROOT / "tests" / "hermes_core" / "fixtures"
                   / "ea4e92pw_one_attempt_screen.cs")
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe",
         "/main:Ea4e92pwOneAttemptScreen", f"/out:{target}",
         *(str(source) for source in sources)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode,expected", [
    ("valid", "CANDIDATE:INPUTS_ONLY"),
    ("share-delete", "DENY:NATIVE_POLICY"),
    ("missing-sid", "DENY:INPUT"),
    ("wrong-child", "DENY:FIRST_CHILD_PATH"),
    ("wrong-manifest", "DENY:MANIFEST_MISMATCH"),
    ("different-descriptor", "DENY:DESCRIPTOR_MISMATCH"),
    ("pre-call", "DENY:PRE_CALL_UNAVAILABLE"),
    ("post-call", "DENY:POST_CALL_UNCERTAIN"),
    ("raw-close", "DENY:RAW_HANDLE_CLOSE_UNCERTAIN"),
    ("wrapper-close-observed", "CANDIDATE:INPUTS_ONLY"),
    ("wrapper-close-unobserved", "DENY:WRAPPER_CLOSE_UNCERTAIN"),
    ("pre-attempt-denial", "CANDIDATE:INPUTS_ONLY"),
    ("post-attempt-denial", "DENY:POST_ATTEMPT_RECONCILIATION_REQUIRED"),
    ("post-attempt-retained", "CANDIDATE:INPUTS_ONLY"),
])
def test_pre_call_screen_only(executable, mode, expected):
    result = subprocess.run(
        [str(executable), mode], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [expected]


def test_owner_is_unwired_and_single_call():
    source = (ROOT / "tools" / "Ea4eDirectory2OneAttemptCandidate.cs").read_text()
    assert source.count("InvokeUnwired(") == 1
    callers = [path.name for path in (ROOT / "tools").glob("Ea4e*.cs")
               if path.name != "Ea4eDirectory2OneAttemptCandidate.cs"
               and "AttemptUnwired(" in path.read_text()]
    assert callers == []


def test_raw_handle_has_pre_wrapper_cleanup_edge():
    source = (ROOT / "tools" / "Ea4eDirectory2OneAttemptCandidate.cs").read_text()
    assert "bool transferred = false;" in source
    assert "owned = new Ea4eDirectoryObservedHandleCandidate(raw);" in source
    assert "if (!transferred)" in source
    assert "bool closed = CloseHandle(raw);" in source
    assert "lastError = observedError;" in source


def test_transferred_handle_has_one_observable_release_edge():
    owner = (ROOT / "tools" / "Ea4eDirectory2OneAttemptCandidate.cs").read_text()
    handle = (ROOT / "tools" / "Ea4eDirectoryObservedHandleCandidate.cs").read_text()
    assert "wrapperCloseUncertain |= !owned.ReleaseObserved;" in owner
    assert "wrapperCloseUncertain |= !accepted.ReleaseObserved;" in owner
    assert "closeError = observedCloseError;" in owner
    assert "ClassifyDisposition(attempted, acceptedResult)" in owner
    assert "observationStatus = result;" in owner
    assert "volumeHex = observedVolume;" in owner
    assert "fileIdHex = observedId;" in owner
    assert "protected override bool ReleaseHandle()" in handle
    assert handle.count("CloseHandle(handle)") == 1
    assert "Marshal.GetLastWin32Error()" in handle
    assert "DangerousGetHandle" not in owner + handle
    assert "SetHandleAsInvalid" not in owner + handle
