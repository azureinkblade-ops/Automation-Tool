"""Tests for storage.root_state_repository (Group A conversion).

Isolated temp DB. Verifies:
- load returns migrated/backfilled data from state_snapshots
- load falls back to the legacy file when DB row absent
- load returns default when both absent
- save persists to state_snapshots and (optionally) mirrors to file
- unknown file constant raises KeyError
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("rsr", ROOT / "storage" / "root_state_repository.py")
rsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rsr)

TMP = Path(tempfile.mkdtemp(prefix="rsr-test-"))


def _fresh_db():
    db = TMP / f"db_{__import__('time').time_ns()}.sqlite"
    return db


def test_load_backfilled():
    db = _fresh_db()
    rsr.save(db, "automaticMetricsState", {"enabled": True, "x": 1})
    got = rsr.load(db, "automaticMetricsState", default={})
    got.pop("_source", None)
    assert got == {"enabled": True, "x": 1}, got


def test_load_file_fallback():
    db = _fresh_db()
    legacy = TMP / "legacy.json"
    legacy.write_text(json.dumps({"a": 2}), encoding="utf-8")
    # DB row absent -> falls back to file
    got = rsr.load(db, "automaticMetricsState", default={}, fallback_file=legacy)
    assert got == {"a": 2}, got
    # and the save also mirrors to file
    rsr.save(db, "automaticMetricsState", {"b": 3}, fallback_file=legacy)
    assert json.loads(legacy.read_text(encoding="utf-8")) == {"b": 3}


def test_load_default_when_absent():
    db = _fresh_db()
    got = rsr.load(db, "storyHookChatgptResult", default={"ok": False})
    assert got == {"ok": False}, got


def test_unknown_constant_raises():
    db = _fresh_db()
    try:
        rsr.load(db, "doesNotExist", default={})
        assert False, "expected KeyError"
    except KeyError:
        pass


if __name__ == "__main__":
    raise SystemExit(1)
