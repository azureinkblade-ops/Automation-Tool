"""SC-7: reversible quarantine of confirmed-dead JSON files.

Moves files out of active paths into _trash-json/<YYYY-MM-DD>/ with a manifest
(hash, size, mtime, classification, reason, source commit). Idempotent: skips
files already quarantined or absent. Restore via tools/restore_trash_json.py.

Usage:
    python tools/quarantine_dead_json.py <path> [<path> ...] --reason "..."

The two SC-3/SC-4 dead mirrors are quarantined here after the SQLite cutover
soak passed (2026-07-23): posting_schedule.json, deep-tiktok-rotation.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRASH_ROOT = ROOT / "_trash-json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _source_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def quarantine(paths: list[Path], reason: str, classification: str = "dead-mirror") -> int:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_dir = TRASH_ROOT / date
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / "manifest.json"

    manifest = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = []

    already = {m.get("original_path") for m in manifest}
    moved = 0
    commit = _source_commit()

    for p in paths:
        p = p.resolve()
        if not p.exists():
            print(f"[skip] absent: {p}")
            continue
        rel = str(p.relative_to(ROOT))
        if rel in already:
            print(f"[skip] already quarantined: {rel}")
            continue
        file_hash = _sha256(p)
        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        target = dest_dir / p.name
        # avoid clobber if same name already in trash
        if target.exists():
            target = dest_dir / f"{p.stem}.{file_hash[:8]}{p.suffix}"
        shutil.move(str(p), str(target))
        # verify hash after move
        moved_hash = _sha256(target)
        entry = {
            "original_path": rel,
            "quarantine_path": str(target.relative_to(TRASH_ROOT)),
            "sha256": file_hash,
            "sha256_after_move": moved_hash,
            "hash_match": file_hash == moved_hash,
            "size_bytes": size,
            "modification_time": mtime,
            "classification": classification,
            "reason": reason,
            "moved_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": commit,
        }
        manifest.append(entry)
        moved += 1
        print(f"[moved] {rel} -> {entry['quarantine_path']} (hash_match={entry['hash_match']})")

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description="SC-7 reversible JSON quarantine")
    ap.add_argument("paths", nargs="+", help="files to quarantine")
    ap.add_argument("--reason", required=True, help="why the file is dead")
    ap.add_argument("--classification", default="dead-mirror")
    args = ap.parse_args()

    paths = [Path(a) for a in args.paths]
    moved = quarantine(paths, args.reason, args.classification)
    print(f"\nQuarantined {moved} file(s). Manifest: {TRASH_ROOT / '_manifest.json' if False else ''}".rstrip())
    print(f"Manifest written under {TRASH_ROOT}/<date>/manifest.json")
    print("Restore with: python tools/restore_trash_json.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
