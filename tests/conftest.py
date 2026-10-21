# -*- coding: utf-8 -*-
"""Mandatory test isolation for Automation Tool (IDENTITY_PUBLISH_AND_TEST_ISOLATION_REMEDIATION).

Fail-closed before any repo tests mutate live state:
- Isolated temp root (Windows-safe timestamp, no colons)
- Redirects SQLite DB, social-posts, tiktok-posts, campaigns, banked/archive paths
- Stubs/redirects promoRotation writers
- If isolation init fails => abort the suite (no live-path fallback)

Sentinel printed at import: TEST_ISOLATION_GUARD_INSTALLED=YES
"""
from __future__ import annotations

# PYTEST_LIVE_SIDE_EFFECT_ISOLATION: install the live side-effect barrier (network/
# subprocess/credential/output) before anything below imports app or any test module.
# Idempotent: the repo-root conftest.py normally installed it already.
import os as _lsi_os, sys as _lsi_sys
_lsi_repo = _lsi_os.path.dirname(_lsi_os.path.dirname(_lsi_os.path.abspath(__file__)))
if _lsi_repo not in _lsi_sys.path:
    _lsi_sys.path.insert(0, _lsi_repo)
from tests import live_side_effect_barrier as _lsi_barrier  # noqa: E402
_lsi_barrier.install()

import os
import sys
import shutil
import sqlite3
import tempfile
import atexit
from datetime import datetime
from pathlib import Path

TEST_ISOLATION_SENTINEL = "TEST_ISOLATION_GUARD_INSTALLED=YES"
TEST_ISOLATION_ABORTS_ON_FAILURE = True
TEST_LIVE_PATH_FALLBACK_ALLOWED = False

_REPO = Path(__file__).resolve().parents[1]
_LIVE_DB = (_REPO / "automation_state.db").resolve()
_LIVE_ROOT = _REPO.resolve()

# Module-level install state (checked by pytest hooks and tests/test_test_isolation.py)
ISOLATION_OK = False
ISOLATION_ROOT: Path | None = None
ISOLATION_ERROR: str = ""
_ORIG_CONNECT = None


def _win_safe_stamp() -> str:
    # Windows-safe: no colons or other invalid path chars
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _abort(msg: str) -> None:
    global ISOLATION_ERROR
    ISOLATION_ERROR = msg
    sys.stderr.write(f"TEST_ISOLATION_ABORT: {msg}\n")
    sys.stderr.flush()
    if TEST_ISOLATION_ABORTS_ON_FAILURE:
        # Use pytest.exit if available; otherwise hard exit
        try:
            import pytest
            pytest.exit(f"TEST_ISOLATION_ABORT: {msg}", returncode=2)
        except Exception:
            raise SystemExit(2)


def _install_isolation() -> None:
    global ISOLATION_OK, ISOLATION_ROOT, _ORIG_CONNECT, ISOLATION_ERROR
    if os.environ.get("AT_TEST_ISOLATION_DISABLE") == "1":
        # Explicit opt-out only for emergency debugging — still not a live fallback default.
        ISOLATION_ERROR = "AT_TEST_ISOLATION_DISABLE=1"
        _abort("AT_TEST_ISOLATION_DISABLE is set; refusing to run without isolation")
        return
    try:
        stamp = _win_safe_stamp()
        # Reject invalid chars defensively
        if any(c in stamp for c in '<>:"|?*'):
            raise RuntimeError(f"isolation stamp has invalid chars: {stamp!r}")
        base = Path(tempfile.gettempdir()) / f"at_iso_{stamp}_{os.getpid()}"
        base.mkdir(parents=True, exist_ok=False)
        (base / "social-posts").mkdir()
        (base / "tiktok-posts").mkdir()
        (base / "campaigns").mkdir()
        (base / "promo-image-archive").mkdir()
        (base / "state").mkdir()
        (base / "docs" / "media").mkdir(parents=True)
        # Fresh empty DB (never copy live DB — tests must not see/write production rows)
        import automation_db
        automation_db.init_db(base)

        ISOLATION_ROOT = base
        os.environ["AT_TEST_ISOLATION_ROOT"] = str(base)
        os.environ["AT_TEST_ISOLATION_SENTINEL"] = TEST_ISOLATION_SENTINEL

        # Redirect sqlite connects that target the live DB path to the sandbox DB.
        _ORIG_CONNECT = sqlite3.connect
        live_db_norm = os.path.normcase(str(_LIVE_DB))
        live_db_str = str(_LIVE_DB)
        sandbox_db = str((base / "automation_state.db").resolve())

        def _iso_connect(database, *a, **k):
            try:
                db_s = os.fspath(database)
            except TypeError:
                db_s = str(database)
            # URI mode=ro against live DB is allowed for explicit read-only diagnostics, but
            # default test paths must never hit live. Redirect any non-ro live open.
            norm = os.path.normcase(os.path.abspath(db_s.split("?")[0].replace("file:", ""))) if isinstance(db_s, str) else ""
            is_live = norm == live_db_norm or db_s == live_db_str or (
                isinstance(db_s, str) and os.path.normcase(db_s.replace("\\", "/")).endswith("/automation_state.db")
                and os.path.normcase(str(_LIVE_ROOT)) in os.path.normcase(os.path.abspath(db_s.split("?")[0].replace("file:", "") or "."))
            )
            if is_live:
                uri = k.get("uri")
                if isinstance(db_s, str) and "mode=ro" in db_s and uri:
                    return _ORIG_CONNECT(database, *a, **k)
                return _ORIG_CONNECT(sandbox_db, *a, **k)
            return _ORIG_CONNECT(database, *a, **k)

        sqlite3.connect = _iso_connect  # type: ignore[assignment]

        # Patch path constants on already-importable / soon-imported modules.
        # Import app_config first (lightweight), then app / promo_builder / buffer / browser.
        import app_config
        app_config.SOCIAL_OUTPUT_DIR = base / "social-posts"
        app_config.TIKTOK_OUTPUT_DIR = base / "tiktok-posts"
        app_config.OUTPUT_DIR = base / "campaigns"

        # automation_db.connect(root) — force sandbox root when callers pass live ROOT
        _real_db_connect = automation_db.connect

        def _db_connect(root):
            try:
                r = Path(root).resolve()
            except Exception:
                r = Path(str(root))
            if r == _LIVE_ROOT or (r / "automation_state.db").resolve() == _LIVE_DB:
                return _real_db_connect(base)
            return _real_db_connect(root)

        automation_db.connect = _db_connect  # type: ignore[assignment]

        _real_db_path = automation_db.db_path

        def _db_path(root):
            try:
                r = Path(root).resolve()
            except Exception:
                r = Path(str(root))
            if r == _LIVE_ROOT:
                return base / "automation_state.db"
            return _real_db_path(root)

        automation_db.db_path = _db_path  # type: ignore[assignment]

        # Import app after path config patches where possible; re-bind its constants.
        import app as app_mod
        app_mod.SOCIAL_OUTPUT_DIR = base / "social-posts"
        app_mod.TIKTOK_OUTPUT_DIR = base / "tiktok-posts"
        app_mod.OUTPUT_DIR = base / "campaigns"
        # Keep ROOT as repo (code/assets live there) but DB helpers already redirected.
        if hasattr(app_mod, "PROMO_IMAGES_DIR"):
            # Prefer not to invent; only redirect archive-like dirs if present
            pass
        for attr, sub in (
            ("GITHUB_MEDIA_DIR", base / "docs" / "media"),
        ):
            if hasattr(app_mod, attr):
                setattr(app_mod, attr, sub)

        try:
            import promo_builder as pb
            if hasattr(pb, "TIKTOK_OUTPUT_DIR"):
                pb.TIKTOK_OUTPUT_DIR = base / "tiktok-posts"
            if hasattr(pb, "SOCIAL_OUTPUT_DIR"):
                pb.SOCIAL_OUTPUT_DIR = base / "social-posts"
        except Exception:
            pass

        try:
            import buffer_publish as buf
            buf.SOCIAL_OUTPUT_DIR = base / "social-posts"
            buf.TIKTOK_OUTPUT_DIR = base / "tiktok-posts"
            buf.OUTPUT_DIR = base / "campaigns"
            buf.YOUTUBE_OUTPUT_DIR = base / "youtube-videos"
            (base / "youtube-videos").mkdir(exist_ok=True)
            buf.EXPERIMENT_OUTPUT_DIR = base / "experiment-post-packs"
            (base / "experiment-post-packs").mkdir(exist_ok=True)
        except Exception:
            pass

        try:
            import browser_publish as br
            br.SOCIAL_OUTPUT_DIR = base / "social-posts"
            br.EXPERIMENT_OUTPUT_DIR = base / "experiment-post-packs"
            (base / "experiment-post-packs").mkdir(exist_ok=True)
        except Exception:
            pass

        # Redirect promo rotation writers that previously mutated live DB via ROOT.
        def _sandbox_root_or(root):
            return base

        # Wrap mirror/load to ensure sandbox
        if hasattr(app_mod, "load_state_snapshot_from_database"):
            _load = app_mod.load_state_snapshot_from_database

            def _iso_load(key, root=None):
                return _load(key, root=base)

            app_mod.load_state_snapshot_from_database = _iso_load  # type: ignore[assignment]

        if hasattr(app_mod, "mirror_state_snapshot_to_database"):
            _mirror = app_mod.mirror_state_snapshot_to_database

            def _iso_mirror(key, state, root=None):
                # Prefer calling underlying with sandbox; fall back to patched load path
                try:
                    return automation_db.upsert_state_snapshot(base, key, state)
                except TypeError:
                    return automation_db.upsert_state_snapshot(base, key, state)

            app_mod.mirror_state_snapshot_to_database = _iso_mirror  # type: ignore[assignment]

        def _cleanup():
            try:
                if _ORIG_CONNECT is not None:
                    sqlite3.connect = _ORIG_CONNECT  # type: ignore[assignment]
            except Exception:
                pass

        atexit.register(_cleanup)

        # Verify sandbox DB exists and is not the live file
        sb = (base / "automation_state.db").resolve()
        if not sb.exists():
            raise RuntimeError("sandbox DB missing after init_db")
        if sb == _LIVE_DB:
            raise RuntimeError("sandbox DB resolved to live DB — refusing")
        # Verify social/tiktok redirects do not resolve into production dirs
        for label, p in (
            ("social", app_mod.SOCIAL_OUTPUT_DIR.resolve()),
            ("tiktok", app_mod.TIKTOK_OUTPUT_DIR.resolve()),
            ("campaigns", app_mod.OUTPUT_DIR.resolve()),
        ):
            if _LIVE_ROOT in p.parents or p == _LIVE_ROOT:
                # allowed only if under temp
                if "at_iso_" not in str(p):
                    raise RuntimeError(f"{label} path still under live repo: {p}")
            live_social = (_LIVE_ROOT / "social-posts").resolve()
            live_tiktok = (_LIVE_ROOT / "tiktok-posts").resolve()
            if p == live_social or p == live_tiktok:
                raise RuntimeError(f"{label} path equals live production dir")

        ISOLATION_OK = True
        print(TEST_ISOLATION_SENTINEL, flush=True)
        print(f"TEST_ISOLATION_ROOT={base}", flush=True)
    except Exception as exc:
        ISOLATION_OK = False
        ISOLATION_ERROR = f"{type(exc).__name__}: {exc}"
        _abort(ISOLATION_ERROR)


# Install immediately on conftest import (before test modules are collected/imported)
_install_isolation()

# SCENE_ENVIRONMENT_LIVE_PATH_REMEDIATION_R3 — Phase 0 + Phase 1 barriers (fail-closed).
# Must be active before any test can reach image generation or runtime state writers.
try:
    from tests.gpu_test_barrier import install_gpu_test_barrier
    install_gpu_test_barrier()
except Exception as _gpu_exc:  # noqa: BLE001
    import sys
    sys.stderr.write(f"GPU_TEST_BARRIER_INSTALL_FAILED: {_gpu_exc}\n")
    sys.stderr.flush()
    raise SystemExit(2)

try:
    from tests.runtime_state_guard import install_runtime_state_guard
    install_runtime_state_guard(sandbox=ISOLATION_ROOT)
except Exception as _rt_exc:  # noqa: BLE001
    import sys
    sys.stderr.write(f"RUNTIME_STATE_GUARD_INSTALL_FAILED: {_rt_exc}\n")
    sys.stderr.flush()
    raise SystemExit(2)


def pytest_configure(config):
    if not config.pluginmanager.has_plugin("tests.live_side_effect_hooks"):
        config.pluginmanager.import_plugin("tests.live_side_effect_hooks")
    if not ISOLATION_OK:
        _abort(ISOLATION_ERROR or "isolation guard not installed")
    # Expose for tests
    config._at_test_isolation_ok = True  # type: ignore[attr-defined]
    config._at_test_isolation_root = ISOLATION_ROOT  # type: ignore[attr-defined]
    # R3 barriers must remain active
    from tests.gpu_test_barrier import GPU_TEST_BARRIER_INSTALLED, generator_guard_active
    from tests.runtime_state_guard import RUNTIME_STATE_TEST_ISOLATION_INSTALLED, runtime_state_guard_active
    if not GPU_TEST_BARRIER_INSTALLED or not generator_guard_active():
        _abort("GPU test barrier missing at pytest_configure")
    if not RUNTIME_STATE_TEST_ISOLATION_INSTALLED or not runtime_state_guard_active():
        _abort("Runtime state guard missing at pytest_configure")


def pytest_sessionstart(session):
    if not ISOLATION_OK or not getattr(session.config, "_at_test_isolation_ok", False):
        _abort("isolation sentinel missing at session start")
    # Independent verification print (packet: print a sentinel; abort if missing)
    print(TEST_ISOLATION_SENTINEL, flush=True)


def pytest_collection_modifyitems(config, items):
    if not ISOLATION_OK:
        _abort("isolation failed before collection completed")
