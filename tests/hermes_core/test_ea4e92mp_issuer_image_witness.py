"""Read-only current executable identity, not protected-install authority."""

import hashlib
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
    target = tmp_path_factory.mktemp("issuer-image-witness") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedIssuerImage.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mp_issuer_image_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run(
        [str(executable), *args], capture_output=True,
        text=True, timeout=10, check=False,
    )


def test_current_executable_path_and_bytes(executable):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    assert call(executable, "current", str(executable), digest).stdout.strip() == (
        "MATCH_IMAGE_BYTES"
    )
    assert call(executable, "current", str(executable), "0" * 64).stdout.strip() == (
        "IMAGE_HASH_MISMATCH"
    )
    assert call(executable, "current", str(executable.parent / "other.exe"), digest
                ).stdout.strip() == "IMAGE_PATH_MISMATCH"


@pytest.mark.parametrize("expected_path,expected_hash,observed_path,observed_hash,reason", [
    ("relative.exe", "a" * 64, "C:\\probe.exe", "a" * 64, "EXPECTED_IMAGE_INVALID"),
    ("C:\\probe.exe", "A" * 64, "C:\\probe.exe", "a" * 64, "EXPECTED_IMAGE_INVALID"),
    ("C:\\probe.exe", "a" * 64, "relative.exe", "a" * 64, "IMAGE_OBSERVATION_INVALID"),
    ("C:\\probe.exe", "a" * 64, "C:\\probe.exe", "bad", "IMAGE_OBSERVATION_INVALID"),
    ("C:\\probe.exe", "a" * 64, "C:\\other.exe", "a" * 64, "IMAGE_PATH_MISMATCH"),
    ("C:\\probe.exe", "a" * 64, "C:\\probe.exe", "b" * 64, "IMAGE_HASH_MISMATCH"),
    ("C:\\probe.exe", "a" * 64, "C:\\probe.exe", "a" * 64, "MATCH_IMAGE_BYTES"),
])
def test_image_comparison(executable, expected_path, expected_hash,
                          observed_path, observed_hash, reason):
    result = call(executable, "fake", expected_path, expected_hash,
                  observed_path, observed_hash)
    assert result.stdout.strip() == reason
    assert (result.returncode == 0) == (reason == "MATCH_IMAGE_BYTES")
