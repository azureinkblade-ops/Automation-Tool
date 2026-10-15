"""Fake-only SQLite P/Invoke round trips; no grant or Docker capability."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "Ea4eProtectedSqlite.cs"
PROBE = ROOT / "tests" / "hermes_core" / "fixtures" / "ea4e92kc_sqlite_probe.cs"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("sqlite-probe") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(SOURCE), str(PROBE)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


@pytest.mark.parametrize("name", ["store.sqlite", "snow-\u96ea.sqlite"])
def test_bound_unicode_commit_reopen_and_rollback(executable, tmp_path, name):
    database = tmp_path / name
    result = subprocess.run(
        [str(executable), str(database)], capture_output=True, text=True,
        timeout=10, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "REOPEN_COMMIT_ROLLBACK_PASS"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM sample").fetchall() == [
            ("quote ' and Unicode \u96ea",),
        ]
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)


def test_relative_store_path_denied(executable, tmp_path):
    result = subprocess.run(
        [str(executable), "relative.sqlite"], cwd=tmp_path,
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 1
    assert "ArgumentException:Absolute SQLite path required" in result.stdout
    assert not (tmp_path / "relative.sqlite").exists()
