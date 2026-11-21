"""PowerShell -Command strings in app.py must survive paths with an apostrophe (task 3c, 2026-11-21). CPU only."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"


def _helper():
    """Load ps_single_quoted from app.py source without importing the whole app."""
    src = APP.read_text(encoding="utf-8")
    m = re.search(r"^def ps_single_quoted\(value: Any\) -> str:\n(?:    .*\n|\n)+?(?=\S)", src, re.M)
    assert m, "ps_single_quoted missing from app.py"
    ns: dict = {"Any": object}
    exec(m.group(0), ns)  # noqa: S102 - our own source
    return ns["ps_single_quoted"]


def test_ps_single_quoted_doubles_apostrophes():
    q = _helper()
    assert q(r"C:\Users\O'Brien\it's here.txt") == r"'C:\Users\O''Brien\it''s here.txt'"
    assert q("plain") == "'plain'"
    assert q(Path("a b") / "c'd") == "'" + str(Path("a b") / "c''d") + "'"


def test_no_unescaped_single_quoted_fstring_paths_in_powershell_commands():
    src = APP.read_text(encoding="utf-8")
    assert not re.findall(r"\"-Command\", f\"[^\"\n]*'\{\w+\}'", src)  # an f-string path inside '...'
    assert src.count("-LiteralPath {ps_single_quoted(") >= 6


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell only")
def test_powershell_reads_a_file_whose_path_has_an_apostrophe(tmp_path):
    folder = tmp_path / "O'Brien's captions"
    folder.mkdir()
    f = folder / "it's.txt"
    f.write_text("caption text", encoding="utf-8")
    cmd = f"Get-Content -Raw -LiteralPath {_helper()(f)}"  # same shape as the clipboard calls, minus Set-Clipboard
    run = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "caption text"
