"""Fresh-process import tests for hand_repair.

These must pass before any wiring into app.py. The package must never pull in
the monolith.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_in_subprocess(module: str) -> tuple[int, str, str]:
    code = (
        "import sys\n"
        f"sys.path.insert(0, r'{REPO_ROOT}')\n"
        f"import {module}\n"
        "print('OK')\n"
        "import sys as _s\n"
        "print('app' if 'app' in _s.modules else 'no-app')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def test_hand_repair_imports_cleanly():
    code, stdout, stderr = _import_in_subprocess("hand_repair")
    assert code == 0, f"import failed: {stderr}"
    assert "OK" in stdout
    assert "no-app" in stdout, "hand_repair must not import app"


def test_hand_repair_service_imports_cleanly():
    code, stdout, stderr = _import_in_subprocess("hand_repair.service")
    assert code == 0, f"import failed: {stderr}"
    assert "OK" in stdout
    assert "no-app" in stdout
