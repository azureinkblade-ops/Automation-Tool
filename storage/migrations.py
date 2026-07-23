"""Idempotent migration ledger for SQLite consolidation.

Adds a checksummed `schema_migrations` table and a `database_metadata` table
on top of the existing automation_db schema. Migrations are registered with
stable IDs and applied in order. The ledger is the source of truth for "did
this migration run", separate from app_meta.schemaVersion.

This module does not rewrite existing tables. It only adds ledger/metadata
tables and future migration steps.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from automation_db import connect  # existing connection factory (WAL, FK on)

LEDGER_TABLE = "schema_migrations"
METADATA_TABLE = "database_metadata"

MIGRATION_ID_BASELINE = "001_baseline_schema_v6"


@dataclass
class Migration:
    migration_id: str
    description: str
    up: Callable[[sqlite3.Connection], None]
    # Stable checksum of the migration definition, for tamper detection.
    checksum: str


def _checksum_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _register_migration(
    migrations: Dict[str, Migration],
    migration_id: str,
    description: str,
    up: Callable[[sqlite3.Connection], None],
    source: str,
) -> None:
    migrations[migration_id] = Migration(
        migration_id=migration_id,
        description=description,
        up=up,
        checksum=_checksum_of(source),
    )


def _ensure_ledger_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            checksum TEXT,
            description TEXT
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (
            metadata_key TEXT PRIMARY KEY,
            metadata_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def baseline_up(conn: sqlite3.Connection) -> None:
    """Record the existing schema-v6 baseline.

    Does not transform existing tables. It only asserts the ledger exists so
    future migrations can depend on a known starting point.
    """
    _ensure_ledger_tables(conn)


def create_schema_migrations_up(conn: sqlite3.Connection) -> None:
    _ensure_ledger_tables(conn)


def create_database_metadata_up(conn: sqlite3.Connection) -> None:
    _ensure_ledger_tables(conn)
    conn.execute(
        f"""
        INSERT INTO {METADATA_TABLE}(metadata_key, metadata_value, updated_at)
        VALUES('created_at', ?, ?)
        ON CONFLICT(metadata_key) DO UPDATE SET metadata_value=excluded.metadata_value, updated_at=excluded.updated_at
        """,
        (_now(), _now()),
    )


def add_analytics_provenance_up(conn: sqlite3.Connection) -> None:
    """SC-6: add raw-source provenance to social_stats_daily.

    Idempotent ALTER: only adds the column if it is absent, so the migration
    is safe to re-run regardless of ledger state. The column is nullable.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(social_stats_daily)").fetchall()}
    if "raw_source_hash" not in cols:
        conn.execute(
            "ALTER TABLE social_stats_daily ADD COLUMN raw_source_hash TEXT"
        )



def build_migrations() -> Dict[str, Migration]:
    """Return the registered migration set.

    Order is by insertion: baseline, ledger, metadata. Future migrations append
    new IDs and their up functions.
    """
    migrations: Dict[str, Migration] = {}

    _register_migration(
        migrations,
        MIGRATION_ID_BASELINE,
        "Record existing schema-v6 baseline after verification",
        baseline_up,
        "baseline_up",
    )
    _register_migration(
        migrations,
        "002_create_schema_migrations",
        "Establish checksummed migration ledger",
        create_schema_migrations_up,
        "create_schema_migrations_up",
    )
    _register_migration(
        migrations,
        "003_create_database_metadata",
        "Add database identity and migration timestamps",
        create_database_metadata_up,
        "create_database_metadata_up",
    )
    _register_migration(
        migrations,
        "004_analytics_provenance",
        "SC-6: add raw_source_hash provenance column to social_stats_daily",
        add_analytics_provenance_up,
        "add_analytics_provenance_up",
    )
    return migrations


def applied_migrations(conn: sqlite3.Connection) -> Dict[str, str]:
    _ensure_ledger_tables(conn)
    rows = conn.execute(
        f"SELECT migration_id, checksum FROM {LEDGER_TABLE}"
    ).fetchall()
    return {r["migration_id"]: r["checksum"] for r in rows}


def pending_migrations(conn: sqlite3.Connection, migrations: Dict[str, Migration]) -> List[Migration]:
    applied = applied_migrations(conn)
    return [m for mid, m in migrations.items() if mid not in applied]


def apply_migrations(root: Path, migrations: Dict[str, Migration] | None = None) -> List[str]:
    """Apply pending migrations in registration order. Returns applied IDs."""
    migrations = migrations if migrations is not None else build_migrations()
    applied_ids: List[str] = []
    with connect(root) as conn:
        _ensure_ledger_tables(conn)
        for mid, m in migrations.items():
            existing = conn.execute(
                f"SELECT checksum FROM {LEDGER_TABLE} WHERE migration_id=?",
                (mid,),
            ).fetchone()
            if existing is not None:
                if existing["checksum"] != m.checksum:
                    raise RuntimeError(
                        f"Migration {mid} checksum mismatch: expected {m.checksum}, found {existing['checksum']}"
                    )
                continue
            m.up(conn)
            conn.execute(
                f"INSERT INTO {LEDGER_TABLE}(migration_id, applied_at, checksum, description) "
                f"VALUES(?, ?, ?, ?)",
                (mid, _now(), m.checksum, m.description),
            )
            applied_ids.append(mid)
    return applied_ids


def record_metadata(root: Path, key: str, value: str) -> None:
    with connect(root) as conn:
        _ensure_ledger_tables(conn)
        conn.execute(
            f"INSERT INTO {METADATA_TABLE}(metadata_key, metadata_value, updated_at) "
            f"VALUES(?, ?, ?) "
            f"ON CONFLICT(metadata_key) DO UPDATE SET metadata_value=excluded.metadata_value, updated_at=excluded.updated_at",
            (key, value, _now()),
        )


def get_metadata(root: Path, key: str) -> Optional[str]:
    with connect(root) as conn:
        _ensure_ledger_tables(conn)
        row = conn.execute(
            f"SELECT metadata_value FROM {METADATA_TABLE} WHERE metadata_key=?",
            (key,),
        ).fetchone()
        return row["metadata_value"] if row else None
