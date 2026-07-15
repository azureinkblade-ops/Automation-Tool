"""Workstream B: launch guard for standalone tool scripts (trackers/watchers).

Counts currently-running python.exe children that this tool launched (matched by the repo
path + a script-name fragment, NOT a naive 'python' substring — see the automation-tool-app
skill's "assemble pattern at runtime" pitfall), and refuses/queues beyond MAX_PARALLEL_SCRIPTS
instead of piling up more RAM-hungry processes.

Usage:
    python tools/run_limited.py tools/track_app_processes.py
    python tools/run_limited.py --max 2 tools/release_upload_tracker.py 21

If at/over the cap, prints a refusal and exits non-zero (callers should treat that as "skip",
not "retry forever"). The script itself is run with a clean env (PYTHONPATH/PYTHONHOME unset)
so it doesn't inherit a broken venv's packages.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL_SCRIPTS", "3"))


def _count_own_children(script_fragment: str) -> int:
    """Count python.exe processes whose command line references this repo + the fragment.

    Avoids matching the guard itself or unrelated python processes by assembling the
    pattern at runtime and requiring both the repo root AND the fragment.
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout
    except Exception:
        return 0
    repo_marker = str(ROOT).replace("\\", "/").lower()
    frag = script_fragment.lower()
    count = 0
    for line in out.splitlines():
        low = line.lower()
        if repo_marker in low and frag in low:
            count += 1
    return count


def main() -> int:
    args = sys.argv[1:]
    max_parallel = DEFAULT_MAX_PARALLEL
    if args and args[0] == "--max":
        max_parallel = int(args[1])
        args = args[2:]
    if not args:
        sys.stderr.write("usage: run_limited.py [--max N] <script.py> [args...]\n")
        return 2

    script = Path(args[0])
    fragment = script.name.lower()
    running = _count_own_children(fragment)
    if running >= max_parallel:
        print(f"[run_limited] REFUSED: {running} instance(s) of {fragment} already running (cap {max_parallel}).")
        return 3

    py = sys.executable
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    # Run in foreground; the caller decides backgrounding. Pass through remaining args.
    return subprocess.run([py, str(script), *args[1:]], env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
