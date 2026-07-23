"""Central database bootstrap and health checks for SQLite consolidation.

Integrates with the existing automation_db.connect/init_db. SC-2 does not
rewrite existing tables; it ensures the migration ledger and metadata tables
exist, applies pending migrations idempotently, and verifies health.

All functions operate on an injectable root so tests use isolated temp DBs and
never touch the live automation_state.db.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import automation_db
from storage import migrations as mig


@dataclass
class HealthReport:
    db_path: str
    exists: bool = False
    size_bytes: int = 0
    quick_check: Optional[str] = None
    foreign_key_check: Optional[str] = None
    required_tables_present: bool = False
    missing_tables: List[str] = field(default_factory=list)
    pending_migrations: int = 0
    schema_version: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def ok(self) -> bool:
        return (
            self.exists
            and self.quick_check == "ok"
            and self.required_tables_present
            and self.pending_migrations == 0
            and not self.errors
        )


REQUIRED_TABLES = [
    "app_meta",
    "state_snapshots",
    "schema_migrations",
    "database_metadata",
]


def initialize_databases(root: Path) -> Path:
    """Idempotent bootstrap: schema-v6 tables + migration ledger + migrations."""
    db_path = automation_db.init_db(root)  # existing 30+ tables, idempotent
    mig.apply_migrations(root)
    return db_path


def verify_database_health(root: Path, required: Optional[List[str]] = None) -> HealthReport:
    required = required or list(REQUIRED_TABLES)
    report = HealthReport(db_path=str(automation_db.db_path(root)))
    path = automation_db.db_path(root)
    report.exists = path.exists()
    if not report.exists:
        report.errors.append("database file does not exist")
        return report

    report.size_bytes = path.stat().st_size
    try:
        with automation_db.connect(root) as conn:
            report.quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
            fk_row = conn.execute("PRAGMA foreign_key_check").fetchone()
            report.foreign_key_check = "ok" if fk_row is None else "violation"

            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = [t for t in required if t not in tables]
            report.missing_tables = missing
            report.required_tables_present = not missing

            applied = mig.applied_migrations(conn)
            all_migrations = mig.build_migrations()
            report.pending_migrations = sum(
                1 for mid in all_migrations if mid not in applied
            )

            row = conn.execute(
                "SELECT value FROM app_meta WHERE key='schemaVersion'"
            ).fetchone()
            report.schema_version = row["value"] if row else None
    except sqlite3.DatabaseError as exc:
        report.errors.append(f"database error: {exc}")
    return report


def automation_db_path_default() -> Path:
    """Default repository root: parent of the `storage` package directory."""
    return Path(__file__).resolve().parents[1]


def backup_database_sqlite(root: Path, backup_path: Path) -> Path:
    """Use the SQLite online backup API. Never copy a live file directly."""
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    src = automation_db.db_path(root)
    if not src.exists():
        raise FileNotFoundError(src)
    with automation_db.connect(root) as conn:
        bck = sqlite3.connect(str(backup_path))
        try:
            conn.backup(bck)
        finally:
            bck.close()
    return backup_path
