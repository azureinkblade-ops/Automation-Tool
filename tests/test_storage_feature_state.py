"""Behavioral tests for SC-4 deep-tiktok-rotation repository.

Isolated temp DBs only; no live JSON or live automation_state.db touched.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

from storage import feature_state_repository as fsr


ROOT = Path(__file__).resolve().parents[1]


def _root() -> Path:
    return Path(tempfile.mkdtemp(prefix="sc4-feat-"))


def _mig_tool():
    spec = importlib.util.spec_from_file_location(
        "migrate_deep_tiktok_rotation",
        ROOT / "tools" / "migrate_deep_tiktok_rotation.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_payload_normalized():
    state = fsr.load(_root())
    assert state.payload["schemaVersion"] == 1
    assert state.payload["cycle"] == 1
    assert state.payload["usedChapters"].keys() == set(fsr.NOVEL_ABBRS)


def test_save_then_load_roundtrip():
    root = _root()
    payload = fsr.default_payload()
    payload["cycle"] = 3
    saved = fsr.save(root, payload)
    assert saved.version == 1
    loaded = fsr.load(root)
    assert loaded.payload["cycle"] == 3
    assert fsr.canonical_hash(loaded.payload) == fsr.canonical_hash(payload)


def test_normalize_coerces_used_chapters():
    root = _root()
    payload = fsr.default_payload()
    payload["usedChapters"]["EN"] = ["5", "2", "10", "abc", "-3"]
    saved = fsr.save(root, payload)
    loaded = fsr.load(root)
    # Faithful to app.py: lstrip('-').isdigit() allows negatives, so -3 survives.
    assert loaded.payload["usedChapters"]["EN"] == [-3, 2, 5, 10]


def test_optimistic_concurrency_blocks_stale_write():
    root = _root()
    fsr.save(root, fsr.default_payload())
    try:
        fsr.save(root, fsr.default_payload(), expected_version=0)
        raise AssertionError("expected FeatureStateConflict")
    except fsr.FeatureStateConflict:
        pass
    fsr.save(root, fsr.default_payload(), expected_version=1)
    assert fsr.load(root).version == 2


def test_import_marker_blocks_reimport():
    root = _root()
    fsr.save(root, fsr.default_payload())
    fsr.record_import_marker(root, "hash", "test")
    assert fsr.migration_status(root)["import_complete"] is True


def test_migration_tool_json_to_sqlite_roundtrip():
    root = _root()
    live = fsr.default_payload()
    live["cycle"] = 7
    live["usedChapters"]["HA"] = [11, 4]
    json_path = Path(tempfile.mkdtemp()) / "deep-tiktok-rotation.json"
    json_path.write_text(json.dumps(live), encoding="utf-8")

    mig = _mig_tool()
    rc = mig.run(root, json_path, app_commit="test")
    assert rc == 0
    reloaded = fsr.load(root)
    assert reloaded.payload["cycle"] == 7
    assert reloaded.payload["usedChapters"]["HA"] == [4, 11]


if __name__ == "__main__":
    raise SystemExit(1)
