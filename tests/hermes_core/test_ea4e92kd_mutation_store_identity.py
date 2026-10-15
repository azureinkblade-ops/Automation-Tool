"""Fake-only durable identity and rollback checks; no grant semantics."""

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SOURCES = [
    ROOT / "tools" / "Ea4eProtectedSqlite.cs",
    ROOT / "tools" / "Ea4eDockerMutationStoreIdentity.cs",
    ROOT / "tests" / "hermes_core" / "fixtures" / "ea4e92kd_store_probe.cs",
]


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("mutation-store") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         *(str(source) for source in SOURCES)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def _call(executable, action, database, anchor, *extra):
    return subprocess.run(
        [str(executable), action, str(database), str(anchor), *extra],
        capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.fixture
def store(executable, tmp_path):
    database = tmp_path / "mutation.sqlite"
    anchor = tmp_path / "mutation.anchor"
    result = _call(executable, "init", database, anchor, "a" * 64, "1")
    assert result.returncode == 0, result.stdout
    return database, anchor


def test_reopen_and_append_only_generations(executable, store):
    database, anchor = store
    for event in ("b" * 64, "c" * 64):
        assert _call(executable, "advance", database, anchor, event).returncode == 0
    assert _call(executable, "open", database, anchor).returncode == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT generation FROM mutation_store_metadata"
        ).fetchone() == ("2",)
        assert connection.execute(
            "SELECT COUNT(*) FROM mutation_store_journal"
        ).fetchone() == (2,)
    assert len(list(anchor.parent.glob(anchor.name + ".g*"))) == 3


def test_reinitialize_conflict_denied(executable, store):
    database, anchor = store
    assert _call(executable, "init", database, anchor, "a" * 64, "1").returncode == 1
    assert _call(executable, "open", database, anchor).returncode == 0


def test_stale_open_cannot_append_after_other_handle_advances(executable, store):
    database, anchor = store
    result = _call(executable, "stale", database, anchor, "b" * 64)
    assert result.returncode == 1
    assert "Concurrent store drift denied" in result.stdout
    assert _call(executable, "open", database, anchor).returncode == 0


def test_rollback_to_old_database_denied(executable, store, tmp_path):
    database, anchor = store
    assert _call(executable, "advance", database, anchor, "b" * 64).returncode == 0
    earlier = tmp_path / "earlier.sqlite"
    shutil.copyfile(database, earlier)
    assert _call(executable, "advance", database, anchor, "c" * 64).returncode == 0
    shutil.copyfile(earlier, database)
    assert _call(executable, "open", database, anchor).returncode == 1


def test_metadata_tamper_denied(executable, store):
    database, anchor = store
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE mutation_store_metadata SET epoch='2'")
    assert _call(executable, "open", database, anchor).returncode == 1


def test_anchor_trailing_bytes_denied(executable, store):
    database, anchor = store
    with (anchor.parent / (anchor.name + ".g00000000")).open("ab") as handle:
        handle.write(b"tamper")
    assert _call(executable, "open", database, anchor).returncode == 1


def test_missing_earlier_anchor_denied(executable, store):
    database, anchor = store
    assert _call(executable, "advance", database, anchor, "b" * 64).returncode == 0
    earlier = anchor.parent / (anchor.name + ".g00000000")
    earlier.rename(anchor.parent / "preserved-earlier-anchor")
    assert _call(executable, "open", database, anchor).returncode == 1


def test_earlier_anchor_hash_tamper_denied(executable, store):
    database, anchor = store
    assert _call(executable, "advance", database, anchor, "b" * 64).returncode == 0
    earlier = anchor.parent / (anchor.name + ".g00000000")
    data = bytearray(earlier.read_bytes())
    data[-1] = ord("a") if data[-1] != ord("a") else ord("b")
    earlier.write_bytes(data)
    assert _call(executable, "open", database, anchor).returncode == 1


def test_journal_tamper_denied(executable, store):
    database, anchor = store
    assert _call(executable, "advance", database, anchor, "b" * 64).returncode == 0
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE mutation_store_journal SET event_hash=?", ("c" * 64,))
    assert _call(executable, "open", database, anchor).returncode == 1


def test_invalid_event_does_not_advance(executable, store):
    database, anchor = store
    assert _call(executable, "advance", database, anchor, "bad").returncode == 1
    assert _call(executable, "open", database, anchor).returncode == 0
    assert len(list(anchor.parent.glob(anchor.name + ".g*"))) == 1
