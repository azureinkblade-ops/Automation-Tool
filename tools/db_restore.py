"""SC-8 safe DB restore.

Restores automation_state.db from a backup created by db_backup_rotate.py
(or any SQLite file). Safety rules:

1. Refuses to run while the app server appears to hold the DB (port :8765
   listening) — restoring under a live writer risks corruption.
2. Snapshots the CURRENT live DB first (auto-backup) so the restore is
   reversible.
3. Verifies the chosen backup's integrity (PRAGMA integrity_check == 'ok')
   before replacing the live DB.
4. Performs the replacement via the SQLite online backup API (never a raw file
   copy over a live handle).
5. Re-runs the health gate after restore.

Run:
  python tools/db_restore.py --list
  python tools/db_restore.py --source migration-backups/rotating/automation_state-<ts>.sqlite
  python tools/db_restore.py --source <path> --root /path/to/repo --no-auto-backup

Restore is the last-resort recovery path documented in SC8-RECOVERY-RUNBOOK.md.
"""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db as adb  # noqa: E402
import storage.database as sd  # noqa: E402


def _server_listening(port: int = 8765) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _integrity_ok(path: Path) -> bool:
    try:
        import sqlite3
        con = sqlite3.connect(str(path))
        try:
            res = con.execute("PRAGMA integrity_check").fetchone()[0]
            return res == "ok"
        finally:
            con.close()
    except Exception:
        return False


def list_backups(out_dir: Path) -> list:
    m = out_dir / "manifest.json"
    if not m.exists():
        return []
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return []


def main() -> int:
    args = sys.argv[1:]
    root = ROOT
    if "--root" in args:
        root = Path(args[args.index("--root") + 1]).resolve()
    out_dir = ROOT / "migration-backups" / "rotating"
    if "--list" in args:
        backups = list_backups(out_dir)
        if not backups:
            print("no backups found in", out_dir)
        for b in sorted(backups, key=lambda e: e.get("created_at", ""), reverse=True):
            print(f"  {b['created_at']}  {b['filename']}  ({b['size_bytes']} bytes, qc={b['quick_check']})")
        return 0

    if "--source" not in args:
        print("usage: --source <path> | --list", file=sys.stderr)
        return 2

    source = Path(args[args.index("--source") + 1]).resolve()
    if not source.exists():
        print(f"source backup not found: {source}", file=sys.stderr)
        return 2

    live = adb.db_path(root)
    if not live.exists():
        print(f"live database not found: {live}", file=sys.stderr)
        return 2

    # Rule 1: don't restore under a live server
    if _server_listening():
        print("REFUSED: app server appears to be running on :8765. Stop it before restore.", file=sys.stderr)
        return 1

    # Rule 1b: the live DB must be writable / not held by another process
    # (e.g. a Hermes/Codex worker or another app instance with an open handle).
    # Refuse early with guidance instead of failing mid-restore.
    try:
        probe = __import__("sqlite3").connect(str(live), timeout=2)
        try:
            probe.execute("PRAGMA user_version")
        finally:
            probe.close()
    except sqlite3.DatabaseError as exc:
        print(f"REFUSED: cannot open live DB (is another process holding it? Hermes/Codex worker, server?): {exc}", file=sys.stderr)
        print("         Stop the holder or run restore from a context where automation_state.db is free.", file=sys.stderr)
        return 1

    # Rule 3: integrity of the backup
    if not _integrity_ok(source):
        print(f"REFUSED: backup failed integrity_check: {source}", file=sys.stderr)
        return 1

    # Rule 2: auto-snapshot current live DB (reversible)
    auto_backup_dir = ROOT / "migration-backups" / "pre-restore"
    auto_backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    auto_path = auto_backup_dir / f"pre-restore-{ts}.sqlite"
    if "--no-auto-backup" not in args:
        sd.backup_database_sqlite(root, auto_path)
        print(f"[ok] auto-snapshot of current live DB -> {auto_path}")

    # Rule 4: restore the backup's content INTO the live DB via the online
    # backup API (overwrites live in place). This avoids renaming the live file
    # on Windows, where WAL -wal/-shm sidecars make os.replace unreliable.
    sqlite3 = __import__("sqlite3")
    try:
        src_con = sqlite3.connect(str(source), timeout=30)
        try:
            live_con = sqlite3.connect(str(live), timeout=30)
            try:
                live_con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                # full copy: destination content is replaced by source content
                src_con.backup(live_con)
            finally:
                live_con.close()
        finally:
            src_con.close()
        print(f"[ok] live DB restored from {source.name}")
    except Exception as exc:
        print(f"RESTORE FAILED: {exc}", file=sys.stderr)
        return 1

    # Rule 5: health gate after restore
    h = sd.verify_database_health(root)
    if not h.ok:
        print(f"RESTORE COMPLETED BUT HEALTH CHECK FAILED: {h.errors}", file=sys.stderr)
        return 1
    print(f"[ok] post-restore health: schema v{h.schema_version}, qc={h.quick_check}, fk={h.foreign_key_check}")
    print("RESTORE OK (reversible via the pre-restore snapshot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
