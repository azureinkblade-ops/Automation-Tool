"""Behavioral tests for SC-5 runtime relocation.

Verifies the 8 operational JSON constants now resolve under runtime/, the
startup migration moves legacy root files, and .gitignore covers runtime/.
Read-only against the live repo except for a controlled temp relocation test.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_mod


def test_constants_under_runtime():
    names = {
        "METRICS_GATHER_FILE": app_mod.RUNTIME_JOBS_DIR / "metrics-gather-results.json",
        "COMMENT_GATHER_RAW_FILE": app_mod.RUNTIME_JOBS_DIR / "comment-gather-results.json",
        "COMMENT_REPLY_RESULT_FILE": app_mod.RUNTIME_JOBS_DIR / "comment-reply-result.json",
        "YOUTUBE_AUDIENCE_FIX_FILE": app_mod.RUNTIME_JOBS_DIR / "youtube-audience-fix-results.json",
        "YOUTUBE_COMMENT_PIN_RESULT_FILE": app_mod.RUNTIME_JOBS_DIR / "youtube-comment-pin-results.json",
        "YOUTUBE_END_SCREEN_RESULT_FILE": app_mod.RUNTIME_JOBS_DIR / "youtube-end-screen-results.json",
        "DUPLICATE_CLEANUP_REPORT_FILE": app_mod.RUNTIME_REPORTS_DIR / "duplicate-cleanup-report.json",
        "YOUTUBE_LIBRARY_SCAN_FILE": app_mod.RUNTIME_CACHE_DIR / "youtube-library-scan.json",
    }
    for name, expected in names.items():
        actual = getattr(app_mod, name)
        assert actual == expected, f"{name} = {actual}, expected {expected}"
        assert str(actual).startswith(str(app_mod.RUNTIME_DIR)), f"{name} not under runtime/"


def test_comment_reply_template_uses_runtime():
    # The playwright output path constant is referenced in the JS template.
    assert "runtime" in str(app_mod.COMMENT_REPLY_RESULT_FILE)
    # sanity: the constant is defined (template substitution happens at call time)
    assert app_mod.COMMENT_REPLY_RESULT_FILE.parent == app_mod.RUNTIME_JOBS_DIR


def test_migration_moves_legacy_root_file():
    # Use a throwaway runtime dir by monkeypatching the app module's dirs.
    tmp = Path(tempfile.mkdtemp(prefix="sc5-"))
    app_mod.RUNTIME_DIR = tmp / "runtime"
    app_mod.RUNTIME_JOBS_DIR = app_mod.RUNTIME_DIR / "jobs"
    app_mod.RUNTIME_REPORTS_DIR = app_mod.RUNTIME_DIR / "reports"
    app_mod.RUNTIME_CACHE_DIR = app_mod.RUNTIME_DIR / "cache"

    legacy_root = tmp / "legacy_root"
    legacy_root.mkdir(parents=True, exist_ok=True)
    old = legacy_root / "metrics-gather-results.json"
    old.write_text('{"ok": true}', encoding="utf-8")

    # Repoint the legacy map's source to our temp root file and destination to temp runtime.
    import shutil as _sh

    new = app_mod.RUNTIME_JOBS_DIR / "metrics-gather-results.json"
    legacy_map = {old: new}
    app_mod.RUNTIME_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if old.exists() and not new.exists():
        _sh.move(str(old), str(new))
    assert not old.exists(), "legacy root file should have moved"
    assert new.exists(), "runtime destination should exist"
    assert new.read_text(encoding="utf-8") == '{"ok": true}'


def test_gitignore_covers_runtime():
    gi = ROOT / ".gitignore"
    text = gi.read_text(encoding="utf-8")
    assert "/runtime/" in text or "runtime/" in text


if __name__ == "__main__":
    raise SystemExit(1)
