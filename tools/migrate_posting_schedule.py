"""One-time posting_schedule.json to SQLite migration (SC-3).

Safe procedure:
1. Back up the live DB via SQLite backup API (never raw file copy).
2. Copy current posting_schedule.json into migration-backups/<ts>/.
3. Export the stale DB row into the same backup dir.
4. Validate the live JSON and import it as authoritative (JSON is newer).
5. Record the import marker.
6. Do NOT delete or quarantine the legacy JSON here; SC-7 handles that after soak.

This tool is idempotent: if the import marker exists, it refuses to re-import
unless --force is passed, so a newer DB state is never clobbered.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script: ensure the repo root is importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import database as db
from storage import schedule_repository as sr


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def run(root: Path, json_path: Path | None = None, force: bool = False, app_commit: str = "unknown") -> int:
    root = Path(root)
    json_path = json_path or (root / "posting_schedule.json")
    if not json_path.exists():
        print(f"ERROR: legacy JSON not found: {json_path}", file=sys.stderr)
        return 2

    status = sr.migration_status(root)
    if status["import_complete"] and not force:
        print("Migration marker already present; refusing to re-import (use --force).")
        print(json.dumps(status, indent=2))
        return 0

    # 1. Backup live DB.
    backup_dir = root / "migration-backups" / _ts()
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / "automation_state.db"
    db.backup_database_sqlite(root, db_backup)
    print(f"DB backup: {db_backup}")

    # 2. Copy current JSON.
    json_backup = backup_dir / "posting_schedule.json"
    shutil.copyfile(json_path, json_backup)
    print(f"JSON backup: {json_backup}")

    # 3. Export stale DB row.
    stale = sr.load(root)
    stale_path = backup_dir / "posting_schedule-db.json"
    stale_path.write_text(
        json.dumps(stale.payload if stale else None, indent=2), encoding="utf-8"
    )
    print(f"DB row export: {stale_path}")

    # 4. Validate and import live JSON.
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    sr.validate(payload)
    sr.save(root, payload)  # version advances from current
    item_count = len(payload.get("novels", []))

    # 5. Record marker.
    src_hash = sr.canonical_hash(payload)
    sr.record_import_marker(root, src_hash, item_count, app_commit)
    print(f"Imported JSON -> SQLite. source_hash={src_hash} items={item_count}")

    # 6. Verify round-trip.
    reloaded = sr.load(root)
    assert reloaded is not None
    assert sr.canonical_hash(reloaded.payload) == src_hash, "round-trip mismatch"
    print("Round-trip verified: DB read equals canonicalized JSON.")
    print("Legacy posting_schedule.json left in place; retire after restart soak (SC-7).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate posting_schedule.json to SQLite")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--app-commit", default="unknown")
    args = parser.parse_args()
    root = Path(args.root) if args.root else db.automation_db_path_default()
    return run(root, Path(args.json) if args.json else None, args.force, args.app_commit)


if __name__ == "__main__":
    raise SystemExit(main())
