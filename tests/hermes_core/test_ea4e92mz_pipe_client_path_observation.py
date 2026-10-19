"""Non-authorizing native pipe-client/path composition checks."""

import os
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
    target = tmp_path_factory.mktemp("pipe-client-path") / "probe.exe"
    sources = [
        "Ea4ePipeClientProcessCandidate.cs",
        "Ea4ePipeClientProcessLeaseCandidate.cs",
        "Ea4ePipeClientTokenCandidate.cs",
        "Ea4eProtectedPathTopologyCandidate.cs",
        "Ea4eProtectedByteSnapshotCandidate.cs",
        "Ea4eProtectedPathAccessCandidate.cs",
        "Ea4ePipeClientPathObservationCandidate.cs",
    ]
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(ROOT / "tools" / source) for source in sources),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92mz_pipe_client_path_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("mode", ["WRITABLE", "KERNEL_WRITABLE",
                                        "KERNEL_WRONG_SID",
                                        "WRONG_SID", "WRONG_PROCESS",
                                        "BAD_HASH", "MISSING",
                                        "EXPECTED_WRITABLE", "EXPECTED_WRONG_PID",
                                        "EXPECTED_WRONG_TIME", "EXPECTED_ZERO_TIME"])
def test_bound_client_path_observation_denies_without_authority(
    executable, tmp_path, mode,
):
    target = tmp_path / "inert.bin"
    target.write_bytes(b"inert")
    if mode == "MISSING":
        target = tmp_path / "absent.bin"
    args = [str(executable), mode, str(target), str(tmp_path)]
    if mode == "WRONG_PROCESS":
        args.append(str(os.getpid()))
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    expected = {
        "WRITABLE": {"DENY:APP_OWNS_OBJECT", "DENY:APP_MUTATION_RIGHTS"},
        "KERNEL_WRITABLE": {"DENY:APP_OWNS_OBJECT", "DENY:APP_MUTATION_RIGHTS"},
        "KERNEL_WRONG_SID": {"DENY:CLIENT_SID_MISMATCH"},
        "WRONG_SID": {"DENY:CLIENT_SID_MISMATCH"},
        "WRONG_PROCESS": {"DENY:CLIENT_PROCESS_MISMATCH"},
        "BAD_HASH": {"DENY:EXPECTED_HASH_INVALID"},
        "MISSING": {"DENY:OPEN_DENIED"},
        "EXPECTED_WRITABLE": {"DENY:APP_OWNS_OBJECT", "DENY:APP_MUTATION_RIGHTS"},
        "EXPECTED_WRONG_PID": {"DENY:APP_PROCESS_IDENTITY_MISMATCH"},
        "EXPECTED_WRONG_TIME": {"DENY:APP_PROCESS_IDENTITY_MISMATCH"},
        "EXPECTED_ZERO_TIME": {"DENY:EXPECTED_APP_PROCESS_INVALID"},
    }
    assert result.stdout.strip() in expected[mode]
