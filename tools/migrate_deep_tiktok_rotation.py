"""One-time deep-tiktok-rotation.json to SQLite migration (SC-4).

Same safe procedure as the schedule migration: DB backup, JSON backup, stale
row export, import JSON as authoritative, record marker. Idempotent unless
--force. Legacy JSON is not deleted here; SC-7 retires it after soak.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script: ensure the repo root is importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import database as db
from storage import feature_state_repository as fsr


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def run(root: Path, json_path: Path | None = None, force: bool = False, app_commit: str = "unknown") -> int:
    root = Path(root)
    json_path = json_path or (root / "deep-tiktok-rotation.json")
    if not json_path.exists():
        print(f"ERROR: legacy JSON not found: {json_path}", file=sys.stderr)
        return 2

    status = fsr.migration_status(root)
    if status["import_complete"] and not force:
        print("Migration marker already present; refusing to re-import (use --force).")
        return 0

    backup_dir = root / "migration-backups" / _ts()
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / "automation_state.db"
    db.backup_database_sqlite(root, db_backup)
    print(f"DB backup: {db_backup}")

    json_backup = backup_dir / "deep-tiktok-rotation.json"
    shutil.copyfile(json_path, json_backup)
    print(f"JSON backup: {json_backup}")

    stale = fsr.load(root)
    (backup_dir / "deep-tiktok-rotation-db.json").write_text(
        json.dumps(stale.payload, indent=2), encoding="utf-8"
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    fsr.save(root, payload)
    src_hash = fsr.canonical_hash(payload)
    fsr.record_import_marker(root, src_hash, app_commit)

    reloaded = fsr.load(root)
    assert fsr.canonical_hash(reloaded.payload) == src_hash, "round-trip mismatch"
    print(f"Imported JSON -> SQLite. source_hash={src_hash}")
    print("Round-trip verified. Legacy deep-tiktok-rotation.json left in place; retire after soak (SC-7).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate deep-tiktok-rotation.json to SQLite")
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--app-commit", default="unknown")
    args = parser.parse_args()
    root = Path(args.root) if args.root else db.automation_db_path_default()
    return run(root, Path(args.json) if args.json else None, args.force, args.app_commit)


if __name__ == "__main__":
    raise SystemExit(main())
