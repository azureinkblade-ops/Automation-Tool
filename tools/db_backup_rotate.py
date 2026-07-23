"""SC-8 rotating DB backup.

Uses the SQLite online backup API (storage.database.backup_database_sqlite) so
it never copies a live file directly. Maintains a manifest and prunes old
backups by count + age retention.

Manifest entry (normalized):
    {
      "path": "<absolute, normcase path>",
      "created_at": "2026-07-23T12:32:18.123456Z",   # UTC ISO 8601 with Z
      "size_bytes": 117440512,
      "sha256": "...",
      "schema_version": "6",
      "quick_check": "ok"
    }

Retention contract (see prune()):
- keep=N  -> preserve the N newest existing backups (minimum retained count).
- max_age_days=D -> remove backups older than D days UNLESS needed to satisfy
  keep=N. When D <= 0, age pruning is disabled and only keep applies.

prune() is deterministic and cwd-independent: every entry is normalized
(relative paths resolved against the backup root, Windows casing normalized,
timestamps parsed defensively with a file-mtime fallback, missing files
ignored) before sorting/deduplicating.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import automation_db as adb  # noqa: E402
import storage.database as sd  # noqa: E402

DEFAULT_KEEP = 20
DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_OUT = ROOT / "migration-backups" / "rotating"

_TS_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",   # preferred: UTC ISO 8601, microseconds
    "%Y-%m-%dT%H:%M:%SZ",      # UTC ISO 8601, seconds
    "%Y-%m-%dT%H:%M:%S",       # local ISO (legacy)
    "%Y-%m-%d %H:%M:%S",       # legacy space-separated local
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_ts(value) -> float | None:
    """Parse a manifest created_at into an epoch float. None if unparseable."""
    if not isinstance(value, str):
        return None
    for fmt in _TS_FORMATS:
        try:
            # datetime.strptime does not understand 'Z'; strip it for the
            # second/minute formats that omit it, but keep microsecond parse.
            candidate = value.replace("Z", "") if fmt.endswith(("Z",)) else value
            return time.mktime(time.strptime(candidate, fmt.replace("Z", "")))
        except ValueError:
            continue
    return None


def backup_once(root: Path, out_dir: Path) -> dict:
    """Take one online backup, return its (normalized) manifest entry.

    The destination filename uses microsecond resolution so rapid successive
    backups never collide and overwrite each other.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    dst = out_dir / f"automation_state-{ts}.sqlite"
    sd.backup_database_sqlite(root, dst)
    size = dst.stat().st_size
    with adb.connect(root) as conn:
        schema = conn.execute("SELECT value FROM app_meta WHERE key='schemaVersion'").fetchone()
        qc = conn.execute("PRAGMA quick_check").fetchone()[0]
    entry = {
        "path": os.path.normcase(str(dst.resolve())),
        "filename": dst.name,
        "size_bytes": size,
        "sha256": _sha256(dst),
        "created_at": _now_utc_iso(),
        "schema_version": schema["value"] if schema else None,
        "quick_check": qc,
    }
    return entry


def load_manifest(out_dir: Path) -> list:
    m = out_dir / "manifest.json"
    if not m.exists():
        return []
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_manifest(out_dir: Path, entries: list) -> None:
    (out_dir / "manifest.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _normalize_entry(entry: dict, out_dir: Path) -> dict | None:
    """Normalize a manifest entry for sorting/dedup.

    - relative paths resolved against out_dir, then resolved to absolute
    - Windows path casing normalized via os.path.normcase
    - timestamp parsed defensively; falls back to file mtime if absent/invalid
    - returns None if the referenced file no longer exists (ignored)
    """
    raw = entry.get("path")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (out_dir / p).resolve()
    else:
        p = p.resolve()
    norm = os.path.normcase(str(p))
    if not p.exists():
        return None
    ts = _parse_ts(entry.get("created_at"))
    mtime = p.stat().st_mtime
    if ts is None:
        ts = mtime  # fall back to file mtime
    return {"entry": entry, "normpath": norm, "ts": ts, "mtime": mtime}


def prune(entries: list, keep: int, max_age_days: int, out_dir: Path) -> list:
    """Return surviving entries; delete the files of dropped entries.

    Selection model (deterministic, cwd-independent):
        normalized = [normalize(e) for e in entries if file exists]
        # dedupe by normalized absolute path (keep newest occurrence)
        by_path = {n.normpath: n for n in normalized}
        items = sorted(by_path.values(),
                        key=lambda n: (n.ts, n.mtime, n.normpath),
                        reverse=True)            # newest first
        protected = items[:keep]                 # keep is the minimum count
        if max_age_days <= 0:
            survivors = items[:keep]
        else:
            max_age_sec = max_age_days * 86400
            now = time.time()
            survivors = [n for n in items
                         if n in protected
                         or (now - n.ts) <= max_age_sec]
    Files for entries not in `survivors` are deleted from disk.
    """
    keep = max(keep, 0)
    normalized = [_normalize_entry(e, out_dir) for e in entries]
    normalized = [n for n in normalized if n is not None]

    # dedupe by normalized absolute path (last occurrence wins = newest)
    by_path: dict[str, dict] = {}
    for n in normalized:
        by_path[n["normpath"]] = n
    items = list(by_path.values())

    # newest first; deterministic tie-breaker (mtime, then normpath)
    items.sort(key=lambda n: (n["ts"], n["mtime"], n["normpath"]), reverse=True)

    protected_paths = {n["normpath"] for n in items[:keep]}
    if max_age_days <= 0:
        survivors = [n for n in items[:keep]]
    else:
        max_age_sec = max_age_days * 86400
        now = time.time()
        survivors = [
            n for n in items
            if n["normpath"] in protected_paths
            or (now - n["ts"]) <= max_age_sec
        ]

    survivor_paths = {n["normpath"] for n in survivors}
    for n in items:
        if n["normpath"] not in survivor_paths:
            p = Path(n["normpath"])
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
    return [n["entry"] for n in survivors]


def take_backup(root: Path, out_dir: Path, keep: int = DEFAULT_KEEP, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict:
    """Full backup cycle: one online backup + append to manifest + prune.

    Returns the new backup's manifest entry. Persists the manifest (after
    pruning, never before) so callers/tests get a consistent on-disk state.
    """
    entry = backup_once(root, out_dir)
    entries = load_manifest(out_dir)
    entries.append(entry)
    survivors = prune(entries, keep, max_age_days, out_dir)
    save_manifest(out_dir, survivors)
    return entry


def main() -> int:
    args = sys.argv[1:]
    keep = DEFAULT_KEEP
    max_age_days = DEFAULT_MAX_AGE_DAYS
    out_dir = DEFAULT_OUT
    root = ROOT
    if "--keep" in args:
        keep = int(args[args.index("--keep") + 1])
    if "--max-age-days" in args:
        max_age_days = int(args[args.index("--max-age-days") + 1])
    if "--out-dir" in args:
        out_dir = Path(args[args.index("--out-dir") + 1]).resolve()
    if "--root" in args:
        root = Path(args[args.index("--root") + 1]).resolve()

    if not adb.db_path(root).exists():
        print(f"database not found at {adb.db_path(root)}", file=sys.stderr)
        return 2

    try:
        entry = take_backup(root, out_dir, keep, max_age_days)
    except Exception as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"[ok] backup -> {entry['filename']} ({entry['size_bytes']} bytes, qc={entry['quick_check']})")
    entries = load_manifest(out_dir)
    print(f"[ok] manifest now holds {len(entries)} backups (kept={keep}, max_age_days={max_age_days})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
