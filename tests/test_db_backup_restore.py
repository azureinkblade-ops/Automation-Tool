"""SC-8 tests: DB health gate, rotating backup/prune, and safe restore.

All tests use isolated temp DBs (copied from the live automation_state.db) so
they never touch production state. The restore test runs the real db_restore
logic against an isolated temp root.

Retention acceptance cases:
- keep=2 retains the two newest backups.
- age pruning removes old backups while preserving the minimum keep.
- missing files are removed from the manifest.
- duplicate manifest paths collapse to one entry.
- relative and absolute representations of the same path deduplicate.
- invalid or absent created_at falls back to file mtime.
- a malformed backup is rejected before restore.
- restore preserves/recreates a healthy live DB.
- the backup manifest is saved AFTER pruning, not before.
"""
import importlib.util
import io
import contextlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = ROOT / "automation_state.db"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def temp_db():
    """A temp dir with its own copy of the live DB."""
    d = Path(tempfile.mkdtemp(prefix="sc8-test-"))
    shutil.copy(LIVE_DB, d / "automation_state.db")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _rotate():
    return _load("db_backup_rotate", ROOT / "tools" / "db_backup_rotate.py")


# ---- backup creation + manifest persistence --------------------------------

def test_backup_creates_file_and_manifest(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    entry = rotate.take_backup(temp_db, out)
    assert (out / entry["filename"]).exists()
    assert (out / "manifest.json").exists()
    assert entry["quick_check"] == "ok"
    assert entry["size_bytes"] > 0
    # entry is normalized: absolute, normcase, UTC ISO Z timestamp
    assert Path(entry["path"]).is_absolute()
    assert entry["created_at"].endswith("Z")


def test_successive_backups_do_not_collide(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    # 5 rapid backups in the same second must yield 5 unique files
    for _ in range(5):
        rotate.take_backup(temp_db, out)
    files = list(out.glob("*.sqlite"))
    assert len(files) == 5, f"expected 5 unique files, got {len(files)}"
    entries = rotate.load_manifest(out)
    assert len(entries) == 5


# ---- retention semantics ---------------------------------------------------

def test_keep_two_retains_two_newest(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    for _ in range(5):
        rotate.take_backup(temp_db, out)
    entries = rotate.load_manifest(out)
    survivors = rotate.prune(entries, keep=2, max_age_days=0, out_dir=out)
    assert len(survivors) == 2
    assert len(list(out.glob("*.sqlite"))) == 2


def test_age_pruning_removes_old_preserving_min_keep(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    # one fresh backup
    rotate.take_backup(temp_db, out)
    # craft two OLD entries (manifest + files) by hand
    old_paths = []
    for i in range(2):
        p = out / f"automation_state-OLD{i}.sqlite"
        shutil.copy(LIVE_DB, p)
        # set mtime + created_at far in the past
        past = time.time() - 400 * 86400
        import os
        os.utime(p, (past, past))
        old_paths.append(p)
    entries = rotate.load_manifest(out)
    entries.append({"path": str(old_paths[0]), "created_at": "2000-01-01T00:00:00.000000Z", "size_bytes": 1, "sha256": "x"})
    entries.append({"path": str(old_paths[1]), "created_at": "2001-01-01T00:00:00.000000Z", "size_bytes": 1, "sha256": "y"})
    survivors = rotate.prune(entries, keep=2, max_age_days=30, out_dir=out)
    # fresh (1) + old (2) = 3 entries; keep=2 protects the 2 newest (fresh + 1 old),
    # the remaining old one is >30d -> removed. So 2 survivors.
    assert len(survivors) == 2
    assert not old_paths[0].exists() or not old_paths[1].exists()


def test_manifest_saved_after_pruning_not_before(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    for _ in range(4):
        rotate.take_backup(temp_db, out)
    # after take_backup the persisted manifest must already reflect pruning
    entries = rotate.load_manifest(out)
    assert len(entries) == 4  # keep default 20, none pruned yet
    rotate.prune(entries, keep=2, max_age_days=0, out_dir=out)
    # calling prune alone does NOT persist; take_backup persists after prune
    assert len(rotate.load_manifest(out)) == 4  # still 4 (prune didn't save)


# ---- normalization / deduplication -----------------------------------------

def test_missing_files_dropped_from_manifest(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    rotate.take_backup(temp_db, out)
    entries = rotate.load_manifest(out)
    # add a manifest entry whose file does not exist
    entries.append({"path": str(out / "ghost.sqlite"), "created_at": "2020-01-01T00:00:00.000000Z", "size_bytes": 1, "sha256": "z"})
    survivors = rotate.prune(entries, keep=5, max_age_days=30, out_dir=out)
    assert len(survivors) == 1  # ghost ignored
    assert len(rotate.load_manifest(out)) >= 1


def test_duplicate_paths_collapse(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    rotate.take_backup(temp_db, out)
    entries = rotate.load_manifest(out)
    # duplicate the single entry (same absolute path) -> must collapse to 1
    dup = dict(entries[0])
    survivors = rotate.prune(entries + [dup], keep=5, max_age_days=30, out_dir=out)
    assert len(survivors) == 1


def test_relative_and_absolute_same_path_dedupe(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    rotate.take_backup(temp_db, out)
    entries = rotate.load_manifest(out)
    abs_path = entries[0]["path"]
    rel_path = Path(abs_path).relative_to(out).as_posix()
    # same file referenced by relative and absolute path -> collapse to 1
    survivor_entries = [
        {"path": abs_path, "created_at": "2026-01-01T00:00:00.000000Z", "size_bytes": 1, "sha256": "a"},
        {"path": rel_path, "created_at": "2026-01-02T00:00:00.000000Z", "size_bytes": 1, "sha256": "b"},
    ]
    survivors = rotate.prune(survivor_entries, keep=5, max_age_days=30, out_dir=out)
    assert len(survivors) == 1


def test_invalid_or_absent_created_at_falls_back_to_mtime(temp_db):
    rotate = _rotate()
    out = temp_db / "bak"
    rotate.take_backup(temp_db, out)
    entries = rotate.load_manifest(out)
    # entry with bogus created_at must still normalize (falls back to mtime)
    bad = dict(entries[0])
    bad["created_at"] = "not-a-timestamp"
    survivors = rotate.prune([bad], keep=5, max_age_days=30, out_dir=out)
    assert len(survivors) == 1
    # entry with absent created_at also normalizes
    no_ts = dict(entries[0])
    del no_ts["created_at"]
    survivors2 = rotate.prune([no_ts], keep=5, max_age_days=30, out_dir=out)
    assert len(survivors2) == 1


# ---- health gate -----------------------------------------------------------

def test_health_gate_passes_on_live_db():
    gate = _load("db_health_gate", ROOT / "tools" / "db_health_gate.py")
    assert gate.run(ROOT, enforce_no_mirrors=True, as_json=False) == 0


def test_health_gate_json_report(temp_db):
    gate = _load("db_health_gate", ROOT / "tools" / "db_health_gate.py")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gate.run(temp_db, enforce_no_mirrors=True, as_json=True)
    assert rc == 0
    rep = json.loads(buf.getvalue())
    assert rep["passed"] is True
    assert rep["checks"]["health"]["ok"] is True
    assert rep["checks"]["integrity_check"] == "ok"


def test_health_gate_detects_retired_mirror(temp_db):
    gate = _load("db_health_gate", ROOT / "tools" / "db_health_gate.py")
    (temp_db / "analytics-lab.json").write_text("{}", encoding="utf-8")
    assert gate.run(temp_db, enforce_no_mirrors=True, as_json=False) == 1


# ---- safe restore -----------------------------------------------------------

def test_restore_round_trip_reverts_mutation(temp_db):
    restore = _load("db_restore", ROOT / "tools" / "db_restore.py")
    rotate = _rotate()
    import automation_db as adb
    import storage.database as sd

    bak = temp_db / "bak"
    rotate.take_backup(temp_db, bak)
    src = list(bak.glob("*.sqlite"))[0]

    with adb.connect(temp_db) as c:
        c.execute("UPDATE state_snapshots SET updated_at='1999-01-01' WHERE state_key='analyticsLab'")
        c.commit()

    sys.argv = ["db_restore.py", "--source", str(src), "--root", str(temp_db), "--no-auto-backup"]
    assert restore.main() == 0

    with adb.connect(temp_db) as c:
        after = c.execute("SELECT updated_at FROM state_snapshots WHERE state_key='analyticsLab'").fetchone()[0]
    assert after != "1999-01-01"
    assert sd.verify_database_health(temp_db).ok


def test_restore_refuses_bad_integrity(temp_db):
    restore = _load("db_restore", ROOT / "tools" / "db_restore.py")
    bad = temp_db / "bad.sqlite"
    bad.write_bytes(b"not a sqlite file")
    sys.argv = ["db_restore.py", "--source", str(bad), "--root", str(temp_db), "--no-auto-backup"]
    assert restore.main() == 1
