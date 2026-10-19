"""Compile the native readback fixture, but exercise only its inert CLI path."""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("native-readback-source") / "probe.exe"
    sources = [
        "Ea4eProtectedIssuerToken.cs",
        "Ea4eProtectedPipeDescriptorScreen.cs",
        "Ea4eProtectedPipeCreatorCandidate.cs",
        "Ea4eProtectedPipeReadbackCandidate.cs",
    ]
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(ROOT / "tools" / name) for name in sources),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nv_native_pipe_readback_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def test_inert_description(executable):
    result = subprocess.run(
        [str(executable), "--describe"], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "SOURCE_ONLY:ONE_PIPE_READBACK_NO_CLIENT"


def test_readback_requests_mandatory_label_without_native_call(executable):
    result = subprocess.run(
        [str(executable), "--readback-flags"], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0000001f"


@pytest.mark.parametrize("args", [[], ["--native-readback"], ["--unknown"]])
def test_incomplete_cli_denied_without_native_call(executable, args):
    result = subprocess.run(
        [str(executable), *args], capture_output=True,
        text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("ceremony,offset,denial,exit_code", [
    ("not-a-guid", 1, "DENY:INPUT", 10),
    ("00000000-0000-0000-0000-000000000000", 1, "DENY:INPUT", 10),
    ("11111111-1111-1111-1111-111111111111", -1, "DENY:DEADLINE", 11),
    ("11111111-1111-1111-1111-111111111111", 5, "DENY:DEADLINE", 11),
])
def test_preflight_denies_without_native_call(executable, ceremony,
                                               offset, denial, exit_code):
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=offset))
    result = subprocess.run(
        [str(executable), "--native-readback", "S-1-5-21-100-200-300-1001",
         "S-1-5-21-100-200-300-1002", ceremony,
         deadline.strftime("%Y-%m-%dT%H:%M:%SZ")],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == exit_code
    assert result.stdout.strip() == denial


@pytest.mark.parametrize("denial,exit_code", [
    ("DENY:READBACK_ACCESS_DENIED", 18),
    ("DENY:READBACK_PRIVILEGE_NOT_HELD", 19),
    ("DENY:READBACK_API_ERROR", 20),
    ("DENY:READBACK_NULL_DESCRIPTOR", 21),
    ("DENY:READBACK_INVALID_DESCRIPTOR", 22),
    ("DENY:DESCRIPTOR_SIZE", 23),
    ("DENY:OWNER_GROUP_OR_ACE_COUNT", 24),
    ("DENY:UNREVIEWED_ACE", 25),
    ("DENY:APP_ACE", 26),
    ("DENY:DUPLICATE_SYSTEM_ACE", 27),
    ("DENY:DUPLICATE_ADMIN_ACE", 28),
    ("DENY:FOREIGN_ACE", 29),
    ("DENY:REQUIRED_ACE_MISSING", 30),
    ("DENY:DESCRIPTOR_SCREEN", 31),
    ("DENY:INVALID_DESCRIPTOR", 32),
    ("DENY:INVALID_HANDLE", 33),
    ("DENY:APP_IDENTITY_NOT_INDIVIDUAL", 36),
    ("DENY:APP_OWNER_OR_OWNER_MISSING", 37),
    ("DENY:DACL_MISSING_OR_UNPROTECTED", 38),
    ("DENY:LABEL_MISSING_OR_UNREVIEWED", 39),
    ("DENY:APP_GRANT_NOT_EXACT", 40),
    ("DENY:BROAD_ALLOW", 41),
    ("DENY:UNTRUSTED_MUTATION_GRANT", 42),
    ("DENY:APP_WRITE_MISSING", 43),
    ("DENY:INVALID_INPUT", 44),
    ("DENY:UNRECOGNIZED", 35),
])
def test_readback_exit_mapping_is_inert(executable, denial, exit_code):
    result = subprocess.run(
        [str(executable), "--classify-readback", denial],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == exit_code
    assert result.stdout.strip() == denial
