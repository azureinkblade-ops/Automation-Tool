"""Exact candidate-byte and mutable-state digests, with no store or issuer."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.hermes_core.test_ea4e92ko_complete_network_grant_candidate import (
    candidate,
    canonical,
)


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("network-grant-digest") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eNetworkGrantV4Digest.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92kq_v4_digest_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run(
        [str(executable), *map(str, args)],
        capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.fixture
def artifacts(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(canonical(candidate()).encode())
    second.write_bytes(canonical(candidate(grant_id="8" * 64)).encode())
    return first, second


def test_exact_row_digest_is_stable(executable, artifacts):
    first, _ = artifacts
    left = call(executable, "row", "a" * 64, first, "ISSUED")
    right = call(executable, "row", "a" * 64, first, "ISSUED")
    assert left.returncode == right.returncode == 0
    assert left.stdout == right.stdout
    assert len(left.stdout.strip()) == 64


def test_row_snapshots_input_bytes(executable, artifacts):
    first, _ = artifacts
    result = call(executable, "snapshot", "a" * 64, first, "ISSUED")
    assert result.returncode == 0
    assert result.stdout.strip() == "SNAPSHOT_OK"


@pytest.mark.parametrize("state", ["CLAIMED", "REVOKED", "UNCERTAIN"])
def test_state_change_changes_row_digest(executable, artifacts, state):
    first, _ = artifacts
    issued = call(executable, "row", "a" * 64, first, "ISSUED")
    changed = call(executable, "row", "a" * 64, first, state)
    assert changed.returncode == 0
    assert issued.stdout != changed.stdout


def test_byte_change_changes_row_digest(executable, artifacts):
    first, second = artifacts
    baseline = call(executable, "row", "a" * 64, first, "ISSUED")
    changed = call(executable, "row", "a" * 64, second, "ISSUED")
    assert baseline.returncode == changed.returncode == 0
    assert baseline.stdout != changed.stdout


def test_table_digest_is_order_independent_but_binds_all_rows(executable, artifacts):
    first, second = artifacts
    left = call(executable, "table", "a" * 64, first, "ISSUED",
                "8" * 64, second, "ISSUED")
    reversed_order = call(executable, "table", "8" * 64, second, "ISSUED",
                          "a" * 64, first, "ISSUED")
    changed_state = call(executable, "table", "a" * 64, first, "CLAIMED",
                         "8" * 64, second, "ISSUED")
    assert left.returncode == reversed_order.returncode == changed_state.returncode == 0
    assert left.stdout == reversed_order.stdout
    assert left.stdout != changed_state.stdout


def test_duplicate_id_denied(executable, artifacts):
    first, second = artifacts
    assert call(executable, "table", "a" * 64, first, "ISSUED",
                "a" * 64, second, "ISSUED").returncode == 1


@pytest.mark.parametrize("grant_id,state", [
    ("bad", "ISSUED"), ("a" * 64, "READY"), ("A" * 64, "ISSUED"),
])
def test_invalid_row_denied(executable, artifacts, grant_id, state):
    first, _ = artifacts
    assert call(executable, "row", grant_id, first, state).returncode == 1


def test_non_ascii_and_unbounded_bytes_denied(executable, artifacts, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{\xff}")
    assert call(executable, "row", "a" * 64, bad, "ISSUED").returncode == 1
    bad.write_bytes(b"x" * 16385)
    assert call(executable, "row", "a" * 64, bad, "ISSUED").returncode == 1
