"""Phase-3 retirement parity check (pre-repoint gate).

Backs up automation_state.db via the SQLite backup API, then canonical-hashes
each kept JSON mirror and its DB payload, reporting match/mismatch. On mismatch
the live JSON is treated as authoritative and imported into the DB (one-time
reconciliation), per the approved order.

Mapping:
- analytics-lab.json          -> state_snapshots['analyticsLab']
- youtube-comment-queue.json  -> state_snapshots['youtubeCommentQueue']
- release_status.json         -> dedicated release_status table (GLOBAL row +
                                 per abbr/chapter rows); reconciled as a whole.

Run: python tools/parity_check_phase3.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db  # noqa: E402
from storage.database import backup_database_sqlite  # noqa: E402


def canon(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def canon_hash(payload: str | object) -> str:
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = payload
    return hashlib.sha256(canon(data).encode("utf-8")).hexdigest()


def backup_db() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dst = ROOT / "migration-backups" / f"phase3-pre-repoint-{ts}.sqlite"
    dst.parent.mkdir(parents=True, exist_ok=True)
    backup_database_sqlite(ROOT, dst)
    print(f"[backup] {dst}")
    return dst


def check_state_blob(fname: str, key: str) -> str:
    src = ROOT / fname
    file_hash = canon_hash(src.read_text(encoding="utf-8")) if src.exists() else None
    row = automation_db.load_state_snapshot(ROOT, key)
    db_hash = canon_hash(row) if row is not None else None
    if file_hash is None and db_hash is None:
        print(f"[skip] {fname}: neither file nor DB present")
        return "skip"
    if file_hash == db_hash:
        print(f"[OK] {fname} == state_snapshots[{key}]  ({file_hash[:12]}...)")
        return "match"
    # mismatch -> JSON authoritative
    if file_hash is not None and db_hash is not None:
        print(f"[MISMATCH] {fname} vs DB -> JSON authoritative")
    elif db_hash is None:
        print(f"[DB-MISSING] {fname} not in DB -> import")
    data = json.loads(src.read_text(encoding="utf-8"))
    automation_db.upsert_state_snapshot(ROOT, key, data)
    print(f"[imported] {fname} -> state_snapshots[{key}]")
    return "imported"


def check_release_status() -> str:
    src = ROOT / "release_status.json"
    if not src.exists():
        print("[skip] release_status.json absent")
        return "skip"
    file_data = json.loads(src.read_text(encoding="utf-8"))
    file_hash = canon_hash(file_data)
    # DB representation: GLOBAL row + all chapter rows, reconstructed
    rows = automation_db.connect(ROOT).execute(
        "SELECT status_key, abbr, chapter, payload_json FROM release_status"
    ).fetchall()
    db_payloads = {r["status_key"]: json.loads(r["payload_json"]) for r in rows}
    db_hash = canon_hash(db_payloads)
    if file_hash == db_hash:
        print(f"[OK] release_status.json == release_status table ({file_hash[:12]}...)")
        return "match"
    print(f"[MISMATCH] release_status.json vs table -> JSON authoritative")
    # Import: mirror the JSON structure into the table the way the app does.
    automation_db.upsert_release_status(ROOT, file_data)
    print("[imported] release_status.json -> release_status table (GLOBAL + chapters)")
    return "imported"


def main() -> int:
    backup_db()
    results = []
    results.append(("analytics-lab.json", check_state_blob("analytics-lab.json", "analyticsLab")))
    results.append(("youtube-comment-queue.json", check_state_blob("youtube-comment-queue.json", "youtubeCommentQueue")))
    results.append(("release_status.json", check_release_status()))
    print("\nParity summary:")
    for f, r in results:
        print(f"  {f}: {r}")
    any_import = any(r in ("imported", "DB-MISSING") for _, r in results)
    print("\nReconciliation performed." if any_import else "\nAll mirrors at parity (no import needed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
