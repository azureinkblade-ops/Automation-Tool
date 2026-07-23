"""Phase-3 retirement enforcement tests (Commit 3, strict scope).

These tests assert the SQLite-only retirement contract:
- Direct writes to retired JSON paths are blocked.
- Direct reads of retired JSON paths fail safe (None + warn).
- Retired keys cannot be re-registered in database_state_files().
- Affected API responses carry typed SQLite references.
- The three large blobs are lazy: NOT loaded during generic startup.
- Bootstrap regression: stale/absent JSON does not clobber newer SQLite.
- Runtime recreation: exercising repointed functions does not regenerate mirrors.

Isolated temp DB/root where the test mutates state. No live production state
is touched.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import storage.retired_state as retired  # noqa: E402
from storage.retired_state import RetiredStateError, RETIRED_STATE_KEYS, RETIRED_BOOTSTRAP_KEYS  # noqa: E402


# --------------------------------------------------------------------------
# 1. Blocked writes to retired paths
# --------------------------------------------------------------------------
def test_write_to_retired_path_raises(tmp_path):
    import release_state

    target = tmp_path / "analytics-lab.json"
    with pytest.raises(RetiredStateError):
        release_state.write_json_atomic(target, {"x": 1})
    assert not target.exists(), "retired mirror must not be created"


def test_write_to_retired_path_via_app_shim_raises(tmp_path):
    import app

    target = tmp_path / "pinned-profile-assets.json"
    with pytest.raises(RetiredStateError):
        app.write_json_atomic(target, {"prompts": []})
    assert not target.exists()


# --------------------------------------------------------------------------
# 2. Blocked reads fail safe
# --------------------------------------------------------------------------
def test_read_of_retired_path_returns_none(tmp_path, capsys):
    import promo_copy

    target = tmp_path / "release_status.json"
    target.write_text(json.dumps({"chapters": {}}), encoding="utf-8")
    assert promo_copy.read_json_safe(target) is None
    captured = capsys.readouterr()
    assert "retired" in captured.err.lower()


# --------------------------------------------------------------------------
# 3. No re-registration of retired bootstrap keys
# --------------------------------------------------------------------------
def test_database_state_files_excludes_retired_keys():
    import app

    keys = set(app.database_state_files().keys())
    leaked = RETIRED_BOOTSTRAP_KEYS & keys
    assert not leaked, f"retired bootstrap keys re-registered: {leaked}"


def test_database_state_files_guards_reregistration(monkeypatch):
    import app

    original = app.database_state_files()

    def fake_map():
        m = dict(original)
        m["youtubeCommentQueue"] = app.ROOT / "youtube-comment-queue.json"
        return m

    monkeypatch.setattr(app, "database_state_files", fake_map)
    with pytest.raises(RuntimeError):
        app.bootstrap_state_database_from_json()


# --------------------------------------------------------------------------
# 4. Typed API responses
# --------------------------------------------------------------------------
def test_mark_pinned_asset_applied_typed_response(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "ROOT", tmp_path)
    monkeypatch.setattr(app, "PINNED_ASSET_PLAN_FILE", tmp_path / "pinned-profile-assets.json")

    # seed a pinned asset so mark_applied can find it
    app.rsr.save(tmp_path, "pinnedProfileAssets", {"prompts": [{"id": "a1", "status": "planned"}]})
    res = app.mark_pinned_asset_applied("a1", "applied")
    assert res["file"] is None
    assert res["storage"] == "sqlite"
    assert res["resource"] == "state_snapshots"
    assert res["state_key"] == "pinnedProfileAssets"


def test_analytics_lab_typed_response(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "ROOT", tmp_path)
    app.rsr.save(tmp_path, "analyticsLab", {"generatedAt": "now"})
    res = app.analytics_lab_dashboard()
    assert res["file"] is None
    assert res["storage"] == "sqlite"
    assert res["resource"] == "state_snapshots"
    assert res["state_key"] == "analyticsLab"


def test_regression_dashboard_typed_response(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "ROOT", tmp_path)
    app.rsr.save(tmp_path, "appRegressionDashboard", {"ok": True})
    res = app.regression_dashboard_status()
    assert res["file"] is None
    assert res["storage"] == "sqlite"
    assert res["resource"] == "state_snapshots"
    assert res["state_key"] == "appRegressionDashboard"


def test_release_status_resource_is_relational(tmp_path, monkeypatch):
    import app
    import automation_db

    monkeypatch.setattr(app, "ROOT", tmp_path)
    automation_db.init_db(tmp_path)
    automation_db.upsert_release_status(tmp_path, {"chapters": {"EN-1": {"abbr": "EN", "chapter": 1}}})
    loaded = app.load_release_status()
    assert isinstance(loaded, dict)
    assert "EN-1" in loaded.get("chapters", {})


# --------------------------------------------------------------------------
# 5. Lazy blobs NOT loaded during generic startup
# --------------------------------------------------------------------------
def test_large_blobs_not_loaded_during_bootstrap(tmp_path, monkeypatch):
    import app
    import storage.root_state_repository as rsr

    monkeypatch.setattr(app, "ROOT", tmp_path)
    automation_db_mod = __import__("automation_db")
    automation_db_mod.init_db(tmp_path)
    # seed the large blobs so a load would be meaningful
    for key in ("analyticsLab", "youtubeCommentQueue", "release_status"):
        if key == "release_status":
            automation_db_mod.upsert_release_status(tmp_path, {"chapters": {}})
        else:
            rsr.save(tmp_path, key, {"seeded": True})

    loaded_keys = []
    orig = rsr.load

    def spy(root, key, default=None, fallback_file=None):
        loaded_keys.append(key)
        return orig(root, key, default=default, fallback_file=fallback_file)

    monkeypatch.setattr(rsr, "load", spy)
    app.bootstrap_state_database_from_json()
    leaked = [k for k in loaded_keys if k in ("analyticsLab", "youtubeCommentQueue")]
    assert not leaked, f"lazy blobs loaded during bootstrap: {leaked}"


# --------------------------------------------------------------------------
# 6. Bootstrap regression: stale/absent JSON does not clobber newer SQLite
# --------------------------------------------------------------------------
def test_absent_json_does_not_clobber_db(tmp_path, monkeypatch):
    import automation_db

    automation_db.init_db(tmp_path)
    automation_db.upsert_state_snapshot(tmp_path, "postRecords", {"newer": True})
    # postRecords JSON absent -> bootstrap must NOT wipe the DB row
    res = automation_db.bootstrap_from_json_files(tmp_path, {"postRecords": tmp_path / "postRecords.json"})
    assert res.get("ok")
    with automation_db.connect(tmp_path) as conn:
        row = conn.execute("SELECT payload_json FROM state_snapshots WHERE state_key='postRecords'").fetchone()
    assert row is not None
    assert json.loads(row[0]).get("newer") is True


def test_read_json_empty_path_no_crash():
    import automation_db

    # The latent bug: read_json(Path("")) normalized to cwd and raised.
    assert automation_db.bootstrap_from_json_files(
        REPO_ROOT, {}
    ).get("ok"), "bootstrap with empty file map must not crash (regression)"


# --------------------------------------------------------------------------
# 7. Runtime recreation: exercising repointed functions does not regenerate mirrors
# --------------------------------------------------------------------------
def test_repointed_functions_do_not_recreate_mirrors(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "ROOT", tmp_path)
    # seed state so functions have something to act on
    app.rsr.save(tmp_path, "pinnedProfileAssets", {"prompts": [{"id": "a1", "status": "planned"}]})
    app.rsr.save(tmp_path, "analyticsLab", {"generatedAt": "now"})
    app.rsr.save(tmp_path, "appRegressionDashboard", {"ok": True})

    # exercise the repointed writers
    app.mark_pinned_asset_applied("a1", "applied")
    app.analytics_lab_dashboard()
    app.regression_dashboard_status()

    recreated = [name for name in retired.RETIRED_FILE_NAMES if (tmp_path / name).exists()]
    assert not recreated, f"retired mirrors regenerated: {recreated}"


def test_retired_state_keys_registry_complete():
    # every retired file name has a registry entry, and vice versa
    assert set(retired.RETIRED_FILE_NAMES) == {v["file"] for v in RETIRED_STATE_KEYS.values()}
    # release_status is the only relational home
    relational = [k for k, v in RETIRED_STATE_KEYS.items() if v.get("relational")]
    assert relational == ["release_status"]
