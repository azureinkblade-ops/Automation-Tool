"""Behavioral tests for SC-3 posting schedule repository.

All against isolated temp DBs. No live JSON or live automation_state.db is
touched. The verification skill requires isolated verification: regression
checks must not mutate live state.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from storage import schedule_repository as sr

ROOT = Path(__file__).resolve().parents[1]


def _root() -> Path:
    return Path(tempfile.mkdtemp(prefix="sc3-sched-"))


def test_create_default_valid():
    sched = sr.create_default()
    sr.validate(sched)  # must not raise


def test_save_then_load_roundtrip():
    root = _root()
    sched = sr.create_default()
    saved = sr.save(root, sched)
    assert saved.version == 1
    loaded = sr.load(root)
    assert loaded is not None
    assert loaded.version == 1
    assert sr.canonical_hash(loaded.payload) == sr.canonical_hash(sched)


def test_load_missing_returns_none():
    root = _root()
    assert sr.load(root) is None


def test_optimistic_concurrency_blocks_stale_write():
    root = _root()
    sched = sr.create_default()
    sr.save(root, sched)  # version 1
    # A second writer that thinks version is still 0 must fail.
    try:
        sr.save(root, sched, expected_version=0)
        raise AssertionError("stale write should have raised ScheduleVersionConflict")
    except sr.ScheduleVersionConflict:
        pass
    # Correct version advances.
    sr.save(root, sched, expected_version=1)
    assert sr.load(root).version == 2


def test_validation_rejects_missing_novels():
    try:
        sr.validate({"foo": "bar"})
        raise AssertionError("expected ScheduleValidationError")
    except sr.ScheduleValidationError:
        pass


def test_import_marker_idempotent_via_status():
    root = _root()
    sched = sr.create_default()
    sr.save(root, sched)
    sr.record_import_marker(root, "abc", 4, "test")
    status = sr.migration_status(root)
    assert status["import_complete"] is True
    assert status["version"] == 1


def test_canonical_hash_stable():
    sched = sr.create_default()
    assert sr.canonical_hash(sched) == sr.canonical_hash(sched)


def test_migration_tool_json_wins_over_stale_db():
    """Mirror the real cutover: live JSON newer than DB snapshot."""
    import importlib.util
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    # Set up a stale DB schedule (old start date).
    stale = sr.create_default()
    stale["releaseQueueStartDate"] = "2026-07-03"
    root = _root()
    sr.save(root, stale)  # DB has old value, version 1
    # Live JSON is newer.
    live = sr.create_default()
    live["releaseQueueStartDate"] = "2026-07-19"
    json_path = tmp / "posting_schedule.json"
    json_path.write_text(json.dumps(live, indent=2), encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        "migrate_posting_schedule", ROOT / "tools" / "migrate_posting_schedule.py"
    )
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    rc = mig.run(root, json_path, app_commit="test")
    assert rc == 0
    reloaded = sr.load(root)
    assert reloaded.payload["releaseQueueStartDate"] == "2026-07-19"
    assert sr.canonical_hash(reloaded.payload) == sr.canonical_hash(live)


def test_migration_refuses_reimport_without_force():
    root = _root()
    sched = sr.create_default()
    sr.save(root, sched)
    sr.record_import_marker(root, "h", 4, "test")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migrate_posting_schedule", ROOT / "tools" / "migrate_posting_schedule.py"
    )
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    json_path = (Path(tempfile.mkdtemp()) / "posting_schedule.json")
    json_path.write_text(json.dumps(sched), encoding="utf-8")
    rc = mig.run(root, json_path)
    assert rc == 0  # refused, not failed
    assert sr.migration_status(root)["import_complete"] is True


if __name__ == "__main__":
    raise SystemExit(1)
