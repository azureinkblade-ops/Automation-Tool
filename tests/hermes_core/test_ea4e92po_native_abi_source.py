"""Reflect the inert five-argument declaration without invoking it."""

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
    target = tmp_path_factory.mktemp("ea4e92po-abi") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eDirectory2NativeAbiCandidate.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92po_native_abi_reflection_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_exact_abi_shape_without_native_call(executable):
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "kernel32.dll:CreateDirectory2W:Unicode:True:Winapi:True",
        "System.IntPtr", "System.String", "System.UInt32", "System.UInt32",
        "System.UInt32", "System.IntPtr",
    ]


def test_no_argument_route(executable):
    result = subprocess.run(
        [str(executable), "create"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


def test_unwired_wrapper_signature_without_native_call(executable):
    result = subprocess.run(
        [str(executable), "wrapper"], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "System.IntPtr", "System.String", "System.UInt32", "System.UInt32",
        "System.UInt32", "System.IntPtr", "System.Int32&",
    ]


def test_wrapper_is_the_only_local_call_site():
    source = (ROOT / "tools" / "Ea4eDirectory2NativeAbiCandidate.cs").read_text()
    assert source.count("CreateDirectory2W(") == 2
    assert "lastError = Marshal.GetLastWin32Error();" in source
    callers = [
        path for path in (ROOT / "tools").glob("Ea4e*.cs")
        if path.name != "Ea4eDirectory2NativeAbiCandidate.cs"
        and "InvokeUnwired(" in path.read_text()
    ]
    assert callers == []
