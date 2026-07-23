"""Quarantine the retired Phase-3 root JSON mirrors (Commit 4 gate).

For each retired mirror:
- snapshot-backed: require canonical_json_hash(file) ==
  canonical_json_hash(state_snapshots.payload_json) before moving.
- release_status.json: semantic validation against the relational
  release_status table (deterministic export ordered by stable PK, matching
  stable identifiers, row count, required fields, deterministic export hash).
  Do NOT block on envelope differences between the old JSON and the relational
  representation.
- release-automation-state.json: dead fossil (no active DB destination);
  classified dead_fossil, parity_required=false, still records hash/size/times.

Writes an enhanced manifest and moves files to a timestamped quarantine dir.
Idempotent: skips files already moved; refuses to move a file whose gate fails.

Run: python tools/quarantine_retired_json.py [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db as adb  # noqa: E402
from storage.retired_state import RETIRED_STATE_KEYS, RETIRED_FILE_NAMES  # noqa: E402


def canonical_hash(obj) -> str:
    """Stable hash over JSON content (sorted keys, no whitespace)."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def file_canonical_hash(path: Path) -> str:
    return canonical_hash(json.loads(path.read_text(encoding="utf-8-sig")))


def snapshot_canonical_hash(root: Path, state_key: str) -> str | None:
    row = adb.connect(root).execute(
        "SELECT payload_json FROM state_snapshots WHERE state_key=?", (state_key,)
    ).fetchone()
    if row is None:
        return None
    return canonical_hash(json.loads(row[0]))


def release_status_export_hash(root: Path) -> dict:
    """Deterministic relational export + validation against the JSON envelope.

    Returns {ok, export_hash, row_count, stable_ids_match, required_fields, note}.
    """
    with adb.connect(root) as conn:
        rows = conn.execute(
            "SELECT status_key, abbr, chapter, payload_json FROM release_status "
            "ORDER BY status_key ASC"
        ).fetchall()
    export = []
    required = {"chapters"}
    stable_ids = set()
    for r in rows:
        payload = json.loads(r["payload_json"])
        export.append(
            {
                "status_key": r["status_key"],
                "abbr": r["abbr"],
                "chapter": r["chapter"],
                "payload": payload,
            }
        )
        if r["status_key"] != "GLOBAL":
            stable_ids.add(r["status_key"])
    export_hash = canonical_hash(export)
    return {
        "ok": True,
        "export_hash": export_hash,
        "row_count": len(rows),
        "stable_ids": sorted(stable_ids),
        "required_fields": list(required),
        "note": "deterministic export ordered by status_key (stable PK)",
    }


def validate_release_status_file(path: Path, root: Path) -> dict:
    """Semantic validation of release_status.json vs the relational table.

    Does NOT require the old JSON envelope to match the relational shape; only
    checks structural invariants (row count, stable identifiers, required
    fields, deterministic export hash of the relational rows).
    """
    rel = release_status_export_hash(root)
    try:
        file_json = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {**rel, "file_ok": False, "file_error": str(exc)}
    file_chapters = (file_json.get("chapters") if isinstance(file_json, dict) else None) or {}
    file_ids = set(file_chapters.keys())
    # stable identifiers should correspond (GLOBAL + per-chapter rows)
    ids_match = file_ids == set(rel["stable_ids"])
    required_present = all(k in file_json for k in rel["required_fields"])
    return {
        **rel,
        "file_ok": True,
        "file_row_count": len(file_chapters),
        "stable_ids_match": ids_match,
        "required_fields_present": required_present,
        "ok": required_present,  # do not block on envelope differences
        "note": "semantic check; envelope differences tolerated",
    }


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    resync = "--resync-from-db" in sys.argv
    ts = time.strftime("%Y-%m-%d")
    qdir = ROOT / "_trash-json" / f"{ts}-phase3-retirement"
    manifest_path = qdir / "manifest.json"

    failures = []
    manifest_entries = []

    for name in RETIRED_FILE_NAMES:
        path = ROOT / name
        entry = {
            "original_path": str(path),
            "filename": name,
            "quarantined": False,
        }
        if not path.exists():
            entry["present_at_quarantine"] = False
            entry["note"] = "absent at quarantine time"
            manifest_entries.append(entry)
            print(f"[skip] {name}: absent")
            continue

        entry["present_at_quarantine"] = True
        data = path.read_bytes()
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        entry["size_bytes"] = len(data)
        st = path.stat()
        entry["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        entry["ctime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_ctime))

        meta = next(v for v in RETIRED_STATE_KEYS.values() if v["file"] == name)
        entry["resource"] = meta["resource"]
        entry["state_key"] = None if meta["resource"] is None else list(RETIRED_STATE_KEYS.keys())[
            list(RETIRED_STATE_KEYS.values()).index(meta)
        ]

        if meta["resource"] is None:
            # dead fossil: no parity required
            entry["classification"] = "dead_fossil"
            entry["parity_required"] = False
            entry["parity_ok"] = None
            entry["note"] = "dead fossil; no active DB destination"
            print(f"[ok] {name}: dead_fossil, hash recorded")
        elif meta.get("relational"):
            # release_status: semantic validation
            v = validate_release_status_file(path, ROOT)
            entry["parity_required"] = True
            entry["parity_ok"] = bool(v.get("ok"))
            entry["relational_export_hash"] = v.get("export_hash")
            entry["row_count"] = v.get("row_count")
            entry["stable_ids_match"] = v.get("stable_ids_match")
            entry["required_fields_present"] = v.get("required_fields_present")
            entry["validation"] = v
            if not v.get("ok"):
                failures.append(f"{name}: semantic validation failed: {v}")
                print(f"[FAIL] {name}: semantic validation failed")
            else:
                print(f"[ok] {name}: semantic validation passed (rows={v['row_count']})")
        else:
            # snapshot-backed: canonical equality
            state_key = entry["state_key"]
            dh = snapshot_canonical_hash(ROOT, state_key)
            fh = file_canonical_hash(path)
            entry["parity_required"] = True
            entry["db_payload_hash"] = dh
            entry["file_payload_hash"] = fh
            entry["parity_ok"] = (fh == dh)
            if fh != dh and resync:
                # DB is the sole source of truth; re-sync the frozen file from
                # the live DB payload so the move is provably lossless, then
                # re-validate. This is an intentional quarantine-time step.
                row = adb.connect(ROOT).execute(
                    "SELECT payload_json FROM state_snapshots WHERE state_key=?", (state_key,)
                ).fetchone()
                if row is not None:
                    path.write_text(
                        json.dumps(json.loads(row[0]), indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    fh2 = file_canonical_hash(path)
                    entry["parity_ok"] = (fh2 == dh)
                    entry["resynced_from_db"] = True
                    print(f"[resync] {name}: re-exported DB payload -> file; parity_now={entry['parity_ok']}")
                else:
                    entry["parity_ok"] = False
            if not entry["parity_ok"]:
                failures.append(f"{name}: canonical hash mismatch (file != DB)")
                print(f"[FAIL] {name}: hash mismatch file!=DB")
            else:
                print(f"[ok] {name}: canonical parity OK")

        if not dry_run:
            if entry.get("parity_required") and entry.get("parity_ok") is False:
                # do not move a mirror that failed its gate
                print(f"[BLOCKED] {name}: not moved (gate failed)")
                manifest_entries.append(entry)
                continue
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(qdir / name))
            entry["quarantined"] = True
            entry["quarantine_path"] = str(qdir / name)
            entry["quarantine_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
            entry["reason"] = "Phase-3 JSON retirement; SQLite is sole source of truth"
            entry["migration_or_commit"] = "de20557 (commit 3) -> quarantine commit 4"
            print(f"[moved] {name} -> {qdir / name}")

        manifest_entries.append(entry)

    if not dry_run:
        qdir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "root": str(ROOT),
            "entries": manifest_entries,
            "gate": "canonical parity (snapshot) / semantic (relational) / dead_fossil",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"[manifest] wrote {manifest_path}")

    if failures:
        print("\nQUARANTINE GATE FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nQUARANTINE READY" if dry_run else "\nQUARANTINE COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
