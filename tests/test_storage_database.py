"""Behavioral tests for SC-2 database bootstrap and migration ledger.

All tests use isolated temp directories. None touch the live
automation_state.db. The verification skill requires isolated verification:
no live state mutation.
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

from storage import database as db
from storage import migrations as mig


def _tmp_root() -> Path:
    base = Path(tempfile.mkdtemp(prefix="sc2-db-"))
    # automation_db uses ROOT / "automation_state.db"; pass ROOT as temp dir.
    return base


def test_missing_db_is_created():
    root = _tmp_root()
    assert not db.automation_db.db_path(root).exists()
    db.initialize_databases(root)
    assert db.automation_db.db_path(root).exists()


def test_missing_parent_directory_created():
    root = _tmp_root() / "nested" / "deep"
    db.initialize_databases(root)
    assert db.automation_db.db_path(root).exists()


def test_idempotent_initialization():
    root = _tmp_root()
    db.initialize_databases(root)
    first = db.verify_database_health(root)
    # Second run must not error and must leave schema intact.
    db.initialize_databases(root)
    second = db.verify_database_health(root)
    assert first.ok() and second.ok()
    assert first.schema_version == second.schema_version


def test_migration_ledger_records_applied():
    root = _tmp_root()
    db.initialize_databases(root)
    applied = mig.applied_migrations(db.automation_db.connect(root))
    assert mig.MIGRATION_ID_BASELINE in applied
    assert "002_create_schema_migrations" in applied
    assert "003_create_database_metadata" in applied


def test_pending_migrations_zero_after_init():
    root = _tmp_root()
    db.initialize_databases(root)
    report = db.verify_database_health(root)
    assert report.pending_migrations == 0


def test_required_tables_present():
    root = _tmp_root()
    db.initialize_databases(root)
    report = db.verify_database_health(root)
    assert report.required_tables_present
    assert report.missing_tables == []


def test_health_quick_check_ok():
    root = _tmp_root()
    db.initialize_databases(root)
    report = db.verify_database_health(root)
    assert report.quick_check == "ok"
    assert report.foreign_key_check == "ok"


def test_health_detects_missing_db():
    root = _tmp_root()
    report = db.verify_database_health(root)
    assert not report.exists
    assert report.ok() is False


def test_migration_checksum_tamper_detection():
    root = _tmp_root()
    db.initialize_databases(root)
    # Re-register with a different checksum to simulate tampering.
    migrations = mig.build_migrations()
    for m in migrations.values():
        m.checksum = "tampered"
    try:
        mig.apply_migrations(root, migrations)
    except RuntimeError as exc:
        assert "checksum mismatch" in str(exc)
    else:
        raise AssertionError("expected checksum mismatch to raise")


def test_backup_uses_sqlite_api_not_file_copy():
    root = _tmp_root()
    db.initialize_databases(root)
    backup = root / "backup" / f"auto-{uuid.uuid4().hex}.db"
    db.backup_database_sqlite(root, backup)
    assert backup.exists()
    # Backup must open as a valid SQLite database.
    with sqlite3.connect(str(backup)) as bck:
        tables = {r[0] for r in bck.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "schema_migrations" in tables


def test_zero_byte_db_handled_by_health():
    root = _tmp_root()
    db_path = db.automation_db.db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"")
    report = db.verify_database_health(root)
    # A zero-byte file exists but cannot pass quick_check; health reports error.
    assert report.exists
    assert report.size_bytes == 0
    assert not report.ok()


def test_metadata_roundtrip():
    root = _tmp_root()
    db.initialize_databases(root)
    mig.record_metadata(root, "migration_run_id", "sc2-test")
    assert mig.get_metadata(root, "migration_run_id") == "sc2-test"


if __name__ == "__main__":
    raise SystemExit(1)
