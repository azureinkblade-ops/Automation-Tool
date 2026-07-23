"""Health CLI entrypoint for SQLite consolidation.

Run: python -m storage.health [--db <root>]

Reports path, quick_check, required tables, pending migrations, and schedule
state without mutating live data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from storage import database as db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite consolidation health check")
    parser.add_argument("--db", default=None, help="Repository root (default: repo parent of storage/)")
    args = parser.parse_args(argv)

    root = Path(args.db) if args.db else db.automation_db_path_default()
    report = db.verify_database_health(root)

    out = {
        "db_path": report.db_path,
        "exists": report.exists,
        "size_bytes": report.size_bytes,
        "quick_check": report.quick_check,
        "foreign_key_check": report.foreign_key_check,
        "required_tables_present": report.required_tables_present,
        "missing_tables": report.missing_tables,
        "pending_migrations": report.pending_migrations,
        "schema_version": report.schema_version,
        "errors": report.errors,
        "ok": report.ok(),
    }
    print(json.dumps(out, indent=2))
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
