"""Test-owned child audit policy and bounded owned-handle cleanup."""

import math
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import url2pathname


def child_audit_policy(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("existing isolated child root required")

    def audit(event, args):
        if event.startswith(("subprocess.", "socket.", "os.exec", "os.spawn")) or event in {
            "os.system", "os.posix_spawn", "os.fork", "ctypes.dlopen",
        }:
            raise RuntimeError(f"child capability prohibited: {event}")
        paths = []
        if event == "open":
            path, mode, flags = args
            if (mode and any(char in mode for char in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                paths = [path]
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "shutil.rmtree"}:
            paths = [args[0]]
        elif event in {"os.rename", "os.link", "os.symlink"}:
            paths = [args[0], args[1]]
        elif event == "sqlite3.connect":
            path = args[0]
            if path == ":memory:":
                return
            if isinstance(path, str) and path.startswith("file:"):
                parsed = urlsplit(path)
                if parsed.netloc not in {"", "localhost"}:
                    raise RuntimeError("remote child SQLite prohibited")
                path = url2pathname(parsed.path)
            paths = [path]
        for value in paths:
            if isinstance(value, int):
                raise RuntimeError("child descriptor mutation prohibited")
            path = Path(os.fsdecode(value)).resolve()
            if not path.is_relative_to(root):
                raise RuntimeError(f"child mutation outside root: {path}")
    return audit


def install_child_guard(root):
    """Install only inside the dedicated child before work-capable imports."""
    sys.dont_write_bytecode = True
    sys.addaudithook(child_audit_policy(root))


class OwnedChildren:
    def __init__(self):
        self.children = []

    def register(self, child):
        if any(existing is child for existing in self.children):
            raise ValueError("child already registered")
        self.children.append(child)

    def cleanup(self, timeout=1.0):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 3:
            raise ValueError("bounded cleanup timeout required")
        failures = []
        for child in self.children:
            try:
                if child.poll() is None:
                    try:
                        child.terminate()
                        child.wait(timeout=timeout)
                    except (OSError, subprocess.TimeoutExpired):
                        child.kill()
                        child.wait(timeout=timeout)
                else:
                    child.wait(timeout=timeout)
                if child.poll() is None:
                    raise RuntimeError("owned child remains alive")
            except Exception as exc:
                failures.append(str(exc))
            finally:
                for name in ("stdin", "stdout", "stderr"):
                    pipe = getattr(child, name, None)
                    if pipe is not None:
                        try:
                            pipe.close()
                        except Exception as exc:
                            failures.append(str(exc))
        if failures:
            raise RuntimeError("owned child cleanup failed: " + "; ".join(failures))
