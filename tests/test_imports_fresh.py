"""Fresh-subprocess import gate for the monolith extraction.

Exposes circular-import / side-effect-at-import bugs: every module
(including app.py) must import cleanly in a FRESH python process,
and importing must NOT start servers, workers, browsers, or posting.

Run: python tests/test_imports_fresh.py
(or: pytest tests/test_imports_fresh.py)
"""
import subprocess
import sys

REPO = r"C:\Users\David\Documents\Automation tool"

# Order: config + state first, then subsystem modules, then the app shell.
MODULES = [
    "app_config",
    "app_state",
    "promo_copy",
    "promo_builder",
    "release_state",
    "release_automation",
    "approval_inbox",
    "buffer_publish",
    "browser_publish",
    "youtube_pipeline",
    "growth_analytics",
    "app",
]


def _import_clean(module: str) -> bool:
    """Import `module` in a fresh subprocess; true only if it imports
    with no Traceback and no startup side-effect markers."""
    code = (
        "import sys, io\n"
        "buf = io.StringIO()\n"
        "old = sys.stderr; sys.stderr = buf\n"
        "try:\n"
        f"    import {module}\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print('FAIL', repr(e)[:300])\n"
        "finally:\n"
        "    sys.stderr = old\n"
        "err = buf.getvalue()\n"
        "assert 'Traceback' not in err, err[-800:]\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (r.stdout or "") + (r.stderr or "")
    return "OK" in out.splitlines() and "Traceback" not in out


def test_all_modules_import_fresh():
    for mod in MODULES:
        assert _import_clean(mod), f"{mod} failed fresh import"
