"""Phase-3 retirement verification.

Checks:
- DB health (schema v6, required tables, no pending migrations, quick_check ok).
- Every retired state_snapshots-backed root JSON has a SQLite snapshot row.
- release_status has relational SQLite rows.
- The retired root JSON mirrors do NOT exist (no silent recreation).
- Bootstrap still runs with the retired keys removed from database_state_files().

Run: python tools/verify_phase3_retirement.py
Exit non-zero on any failure (CI gate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db  # noqa: E402
import storage.database as sd  # noqa: E402
import app as _app  # noqa: E402
from storage.retired_state import RETIRED_FILE_NAMES, RETIRED_STATE_KEYS  # noqa: E402


RETIRED_ROOT_FILES = list(RETIRED_FILE_NAMES)


def main() -> int:
    failures = []

    h = sd.verify_database_health(ROOT)
    if not h.ok:
        failures.append(f"DB health failed: {h.errors} missing={h.missing_tables} pending={h.pending_migrations}")
    else:
        print(f"[ok] DB health: schema v{h.schema_version}, quick_check={h.quick_check}, fk={h.foreign_key_check}")

    # bootstrap must still run (retired keys removed from database_state_files)
    try:
        res = automation_db.bootstrap_from_json_files(ROOT, _app.database_state_files())
        if not res.get("ok"):
            failures.append(f"bootstrap failed: {res}")
        else:
            print("[ok] bootstrap_from_json_files ran with retired keys removed")
    except Exception as exc:
        failures.append(f"bootstrap raised: {exc}")

    # enforcement: retired bootstrap keys must not be re-registered
    try:
        from storage.retired_state import RETIRED_BOOTSTRAP_KEYS

        leaked = RETIRED_BOOTSTRAP_KEYS & set(_app.database_state_files().keys())
        if leaked:
            failures.append(f"database_state_files re-registered retired keys: {sorted(leaked)}")
        else:
            print("[ok] database_state_files excludes retired bootstrap keys")
    except Exception as exc:
        failures.append(f"retirement enforcement check raised: {exc}")

    with automation_db.connect(ROOT) as conn:
        for state_key, meta in RETIRED_STATE_KEYS.items():
            if meta.get("resource") != "state_snapshots":
                continue
            row = conn.execute("SELECT 1 FROM state_snapshots WHERE state_key=?", (state_key,)).fetchone()
            if not row:
                failures.append(f"{state_key} missing from state_snapshots")
            else:
                print(f"[ok] {state_key} present in state_snapshots")
        rs = conn.execute("SELECT COUNT(*) FROM release_status").fetchone()[0]
        if rs == 0:
            failures.append("release_status table empty")
        else:
            print(f"[ok] release_status table has {rs} rows")

    # retired root mirrors must not exist (no silent recreation).
    # This is a HARD gate only after the repoint (Commit 2+). Before the
    # repoint the app still writes these files, so we report it as
    # informational here and enforce it post-repoint via --enforce-no-mirrors.
    recreated = [f for f in RETIRED_ROOT_FILES if (ROOT / f).exists()]
    if recreated:
        if "--enforce-no-mirrors" in sys.argv:
            failures.append(f"retired mirrors recreated at root: {recreated}")
        else:
            print(f"[info] {len(recreated)} retired mirrors still present at root "
                  f"(expected before repoint; enforced after Commit 2)")
    else:
        print("[ok] no retired root JSON mirrors present")

    if failures:
        print("\nPHASE-3 VERIFICATION FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPHASE-3 RETIREMENT VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
