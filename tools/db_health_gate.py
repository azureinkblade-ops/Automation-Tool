"""SC-8 health gate: single CLI entry point for DB health + integrity + Phase-3
retirement enforcement.

Composes the existing primitives (storage.database.verify_database_health,
PRAGMA integrity, and the retirement mirror check) into one CI gate.

Exit codes:
  0  all checks passed
  1  one or more checks failed
  2  usage / environment error (e.g. DB missing)

Run:
  python tools/db_health_gate.py                 # health + integrity + soft mirror info
  python tools/db_health_gate.py --enforce-no-mirrors
  python tools/db_health_gate.py --json          # machine-readable report
  python tools/db_health_gate.py --root /path/to/repo

Does NOT modify the database. Read-only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db as adb  # noqa: E402
import storage.database as sd  # noqa: E402
from storage.retired_state import RETIRED_FILE_NAMES  # noqa: E402

RETIRED_ROOT_FILES = list(RETIRED_FILE_NAMES)


def run(root: Path, enforce_no_mirrors: bool, as_json: bool) -> int:
    report = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "root": str(root), "checks": {}}
    failures = []

    # 1) database health (schema, tables, pending migrations, quick_check)
    try:
        h = sd.verify_database_health(root)
        report["checks"]["health"] = {
            "exists": h.exists,
            "schema_version": h.schema_version,
            "quick_check": h.quick_check,
            "foreign_key_check": h.foreign_key_check,
            "required_tables_present": h.required_tables_present,
            "missing_tables": h.missing_tables,
            "pending_migrations": h.pending_migrations,
            "ok": h.ok(),
        }
        if not h.ok:
            failures.append(f"health: {h.errors} missing={h.missing_tables} pending={h.pending_migrations}")
    except Exception as exc:
        report["checks"]["health"] = {"ok": False, "error": str(exc)}
        failures.append(f"health raised: {exc}")

    # 2) integrity: PRAGMA integrity_check (deeper than quick_check)
    try:
        with adb.connect(root) as conn:
            ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
        report["checks"]["integrity_check"] = ic
        if ic != "ok":
            failures.append(f"integrity_check: {ic}")
    except Exception as exc:
        report["checks"]["integrity_check"] = {"error": str(exc)}
        failures.append(f"integrity_check raised: {exc}")

    # 3) Phase-3 retirement enforcement: no retired mirrors at root
    recreated = [f for f in RETIRED_ROOT_FILES if (root / f).exists()]
    report["checks"]["retired_mirrors_present"] = recreated
    if recreated and enforce_no_mirrors:
        failures.append(f"retired mirrors present at root: {recreated}")

    report["passed"] = not failures
    report["failures"] = failures

    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[{'ok' if report['checks'].get('health', {}).get('ok') else 'FAIL'}] health")
        print(f"[{'ok' if report['checks'].get('integrity_check') == 'ok' else 'FAIL'}] integrity_check")
        if recreated:
            print(f"[{'FAIL' if enforce_no_mirrors else 'info'}] retired mirrors present: {recreated}")
        else:
            print("[ok] no retired mirrors at root")
        if failures:
            print("\nHEALTH GATE FAILED:")
            for f in failures:
                print("  -", f)
        else:
            print("\nHEALTH GATE PASSED")

    return 0 if not failures else 1


def main() -> int:
    args = sys.argv[1:]
    enforce = "--enforce-no-mirrors" in args
    as_json = "--json" in args
    root = ROOT
    if "--root" in args:
        i = args.index("--root")
        if i + 1 >= len(args):
            print("--root requires a path", file=sys.stderr)
            return 2
        root = Path(args[i + 1]).resolve()
    if not adb.db_path(root).exists():
        print(f"database not found at {adb.db_path(root)}", file=sys.stderr)
        return 2
    return run(root, enforce, as_json)


if __name__ == "__main__":
    raise SystemExit(main())
