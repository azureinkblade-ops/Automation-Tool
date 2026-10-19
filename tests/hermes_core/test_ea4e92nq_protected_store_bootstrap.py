"""Protected-store zero-generation bootstrap only; no issue or Docker path."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
SCHEMA = "hermes.docker-network-grant-store/protected-v1"


@pytest.fixture(scope="module")
def executable(tmp_path_factory):
    if sys.platform != "win32" or not CSC.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    target = tmp_path_factory.mktemp("protected-store-bootstrap") / "probe.exe"
    result = subprocess.run(
        [str(CSC), "/nologo", "/target:exe", f"/out:{target}",
         str(ROOT / "tools" / "Ea4eProtectedSqlite.cs"),
         str(ROOT / "tools" / "Ea4eProtectedNetworkGrantStoreBootstrap.cs"),
         str(ROOT / "tests" / "hermes_core" / "fixtures"
             / "ea4e92nq_protected_store_bootstrap_probe.cs")],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return target


def call(executable, *args):
    return subprocess.run(
        [str(executable), *(str(arg) for arg in args)],
        capture_output=True, text=True, timeout=10, check=False,
    )


@pytest.fixture
def store(executable, tmp_path):
    db = tmp_path / "protected.sqlite"
    anchor = tmp_path / "protected.anchor"
    result = call(executable, "init", db, anchor, "a" * 64, 1)
    assert result.returncode == 0, result.stderr
    return db, anchor


def test_separate_schema_and_reopen(executable, store):
    db, anchor = store
    assert call(executable, "open", db, anchor).returncode == 0
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT schema_id,generation FROM protected_grant_metadata"
        ).fetchone() == (SCHEMA, "0")
        assert connection.execute(
            "SELECT COUNT(*) FROM protected_grant_rows"
        ).fetchone() == (0,)


def test_duplicate_init_denied(executable, store):
    db, anchor = store
    assert call(executable, "init", db, anchor, "a" * 64, 1).returncode == 1
    assert call(executable, "open", db, anchor).returncode == 0


@pytest.mark.parametrize("field,value", [
    ("schema_id", "hermes.docker-mutation-store-identity/v3"),
    ("store_id", "b" * 64),
    ("epoch", "2"),
    ("generation", "1"),
    ("state_hash", "b" * 64),
])
def test_metadata_tamper_denied(executable, store, field, value):
    db, anchor = store
    with sqlite3.connect(db) as connection:
        connection.execute(f"UPDATE protected_grant_metadata SET {field}=?", (value,))
    assert call(executable, "open", db, anchor).returncode == 1


def test_anchor_tamper_denied(executable, store):
    db, anchor = store
    anchor.write_bytes(anchor.read_bytes() + b"x")
    assert call(executable, "open", db, anchor).returncode == 1


@pytest.mark.parametrize("table,values", [
    ("protected_grant_events", (1, "a", "b", "c")),
    ("protected_grant_rows", ("a", "b", "c", "d", "ISSUED", "1")),
])
def test_unqualified_row_denied(executable, store, table, values):
    db, anchor = store
    with sqlite3.connect(db) as connection:
        connection.execute(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
        )
    assert call(executable, "open", db, anchor).returncode == 1


def test_fake_store_cannot_open(executable, tmp_path):
    db = tmp_path / "fake.sqlite"
    anchor = tmp_path / "fake.anchor"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE mutation_store_metadata (schema_id TEXT)")
        connection.execute(
            "INSERT INTO mutation_store_metadata VALUES (?)",
            ("hermes.docker-mutation-store-identity/v3",),
        )
    anchor.write_text("fake", encoding="ascii")
    assert call(executable, "open", db, anchor).returncode == 1


def test_bad_identity_or_epoch_denied(executable, tmp_path):
    db = tmp_path / "bad.sqlite"
    anchor = tmp_path / "bad.anchor"
    assert call(executable, "init", db, anchor, "bad", 1).returncode == 1
    assert call(executable, "init", db, anchor, "a" * 64, 0).returncode == 1
    assert not db.exists() and not anchor.exists()
