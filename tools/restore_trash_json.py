"""SC-7: reversible restore of quarantined JSON files.

Restores files from the most recent _trash-json/<date>/manifest.json back to
their original paths, verifying the hash matches before moving. Idempotent:
skips files whose original path already exists (unless --force).

Usage:
    python tools/restore_trash_json.py [--date YYYY-MM-DD] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRASH_ROOT = ROOT / "_trash-json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_manifest() -> tuple[Path, list[dict]] | tuple[None, list]:
    if not TRASH_ROOT.exists():
        return None, []
    manifests = sorted(
        TRASH_ROOT.glob("*/manifest.json"),
        key=lambda p: p.parent.name,
        reverse=True,
    )
    for m in manifests:
        try:
            return m, json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None, []


def restore(date: str | None = None, force: bool = False) -> int:
    if date:
        manifest_path = TRASH_ROOT / date / "manifest.json"
        if not manifest_path.exists():
            print(f"[error] no manifest for {date}")
            return 1
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest_path, manifest = _latest_manifest()
        if not manifest:
            print("[error] no quarantine manifest found")
            return 1

    restored = 0
    for entry in manifest:
        orig = ROOT / entry["original_path"]
        qpath = TRASH_ROOT / entry["quarantine_path"]
        if not qpath.exists():
            print(f"[skip] quarantine file missing: {entry['quarantine_path']}")
            continue
        if orig.exists() and not force:
            print(f"[skip] original exists (use --force): {entry['original_path']}")
            continue
        current_hash = _sha256(qpath)
        if current_hash != entry.get("sha256"):
            print(f"[skip] hash mismatch (tampered?): {entry['original_path']}")
            continue
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(qpath), str(orig))
        restored += 1
        print(f"[restored] {entry['original_path']}")
    print(f"\nRestored {restored} file(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SC-7 restore quarantined JSON")
    ap.add_argument("--date", help="specific quarantine date YYYY-MM-DD")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return restore(args.date, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
