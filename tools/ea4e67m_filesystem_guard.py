"""Python audit tripwire limiting test mutations to explicit temporary storage."""

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import url2pathname

import pytest


_active = False
_root = None
_events = []
_environment = {}
_tempdir = None
_bytecode = None


def validate_path(value, root):
    if isinstance(value, int):
        raise RuntimeError("unqualified file descriptor mutation")
    path = Path(os.fsdecode(value)).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError(f"filesystem mutation outside test root: {path}")


def audit(event, args):
    if not _active:
        return
    paths = []
    if event == "open":
        path, mode, flags = args
        if not isinstance(path, int) and Path(os.fsdecode(path)).resolve() == Path(os.devnull).resolve():
            return
        if (mode and any(flag in mode for flag in "wax+")) or (
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        ):
            paths = [path]
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime",
                   "shutil.rmtree", "sqlite3.connect"}:
        if event == "sqlite3.connect" and args[0] == ":memory:":
            return
        paths = [args[0]]
    elif event in {"os.rename", "os.link", "os.symlink"}:
        paths = [args[0], args[1]]
    try:
        for path in paths:
            if event == "sqlite3.connect" and isinstance(path, str) and path.startswith("file:"):
                parsed = urlsplit(path)
                if parsed.netloc not in {"", "localhost"}:
                    raise RuntimeError("remote SQLite URI prohibited")
                path = url2pathname(parsed.path)
            validate_path(path, _root)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        _events.append(f"{event}: {exc}")
        raise RuntimeError(f"EA4E67M_FILESYSTEM_TRIPWIRE: {event}: {exc}") from exc


def pytest_configure(config):
    global _active, _root, _tempdir, _bytecode
    if not config.option.basetemp:
        raise pytest.UsageError("filesystem guard requires explicit fresh basetemp")
    root = Path(config.option.basetemp).resolve()
    repo = Path(__file__).resolve().parents[1]
    if not root.is_relative_to(repo) or root == repo or root.exists():
        raise pytest.UsageError("filesystem guard requires fresh test root inside export/worktree")
    _root = root
    _tempdir = tempfile.tempdir
    _bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    for name in ("TEMP", "TMP"):
        _environment[name] = os.environ.get(name)
        os.environ[name] = str(root / "temporary")
    sys.addaudithook(audit)
    _active = True


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    # Ask pytest to establish its own root before putting tempfile storage in it.
    root = session.config._tmp_path_factory.getbasetemp()
    temporary = root / "temporary"
    temporary.mkdir()
    tempfile.tempdir = str(temporary)


def pytest_sessionfinish(session, exitstatus):
    if _events:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E67M_FILESYSTEM_TRIPWIRE_EVENTS={len(_events)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    global _active
    _active = False
    tempfile.tempdir = _tempdir
    sys.dont_write_bytecode = _bytecode
    for name, value in _environment.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _environment.clear()
