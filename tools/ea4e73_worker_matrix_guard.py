"""Original worker/coordinator qualification, with bounded test-only routing."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

from tools import ea4e67m_filesystem_guard as filesystem
from tools import ea4e67y_worker_admission as admission
from tools.ea4e67z_worker_containment import OwnedChildren
from tools.ea4e71_owned_pipe_scope import OwnedPipeScope
from tools.ea4e72_child_probe_guard import verify_sources


MISSING = admission.WORKER + "RealSpawnTests::test_executable_missing_fails_closed"
SYNC = admission.WORKER + "TimeoutMechanicsTests::test_synchronous_creation_yields_handle_or_definitive_failure"
_node = None
_admitted = {}
_missing = {}
_events = []
_originals = []
_owned = OwnedChildren()
_pipe_opens = 0


def validate_options(options, base):
    required = {"cwd", "env", "shell", "stdin", "stdout", "stderr", "text", "encoding", "errors", "creationflags"}
    if set(options) != required or Path(options["cwd"]).resolve() != admission.ROOT:
        raise ValueError("matrix options/cwd denied")
    if options["creationflags"] != (getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0):
        raise ValueError("matrix Windows flags denied")
    if options["shell"] is not False or options["text"] is not True or options["encoding"] != "utf-8" or options["errors"] != "replace":
        raise ValueError("matrix text/shell denied")
    if any(options[name] != subprocess.PIPE for name in ("stdin", "stdout", "stderr")):
        raise ValueError("matrix pipes denied")
    environment = options["env"]
    if set(environment) - {"SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"}:
        raise ValueError("matrix environment denied")
    if any(environment.get(name) != os.environ.get(name) for name in ("SYSTEMROOT", "SYSTEMDRIVE")):
        raise ValueError("matrix system environment denied")
    for name in ("TEMP", "TMP"):
        if name not in environment or not Path(environment[name]).resolve().is_relative_to(base):
            raise ValueError("matrix temporary environment denied")


def missing_executable_case(node, command, options, base, counts):
    if node not in {MISSING, SYNC} or counts.get(node, 0) != 0:
        raise ValueError("missing-executable node/budget denied")
    expected_length = 3 if node == MISSING else 2
    if (not isinstance(command, list) or len(command) != expected_length
            or command[:2] != ["C:/does/not/exist/python.exe", str(admission.HELPER)]
            or Path(command[0]).exists()):
        raise ValueError("missing-executable identity denied")
    validate_options(options, base)
    verify_sources()
    if len(command) == 3:
        admission.validate_worker_launch(admission.WORKER + "RealSpawnTests::test_valid_probe_returns_started",
                                         [str(admission.PYTHON), *command[1:]], options["cwd"], options["env"], base, {})


def pytest_addoption(parser):
    parser.addoption("--ea4e73-original-worker-matrix", action="store_true", default=False)


def pytest_configure(config):
    if not config.getoption("--ea4e73-original-worker-matrix") or not config.option.basetemp:
        raise pytest.UsageError("explicit original-worker matrix envelope required")
    verify_sources()
    base = Path(config.option.basetemp).resolve()
    original = subprocess.Popen
    scope = OwnedPipeScope(original.__init__.__code__)
    original_validate = filesystem.validate_path

    def validate_owned_pipe(value, root):
        global _pipe_opens
        frame = sys._getframe(1)
        if (type(value) is int and frame.f_code is filesystem.audit.__code__
                and scope.allows(frame.f_locals.get("event"), frame.f_locals.get("args", ()), frame.f_back)):
            _pipe_opens += 1
            return
        return original_validate(value, root)

    def guarded(command, *args, **options):
        try:
            if args or not isinstance(command, list):
                raise ValueError("matrix process call denied")
            if command and command[0] == "C:/does/not/exist/python.exe":
                missing_executable_case(_node, command, options, base, _missing)
                _missing[_node] = _missing.get(_node, 0) + 1
                raise FileNotFoundError("qualified missing executable; no constructor invoked")
            validate_options(options, base)
            admission.validate_worker_launch(_node, command, options["cwd"], options["env"], base, _admitted)
            verify_sources()
        except FileNotFoundError:
            raise
        except Exception as exc:
            _events.append(str(exc))
            raise RuntimeError("EA4E73 process denied: " + str(exc)) from exc
        _admitted[_node] = _admitted.get(_node, 0) + 1
        wrapped = [command[0], "-B", str(admission.ROOT / "tools/ea4e68_worker_entrypoint.py"), _node, str(base), *command]
        with scope.creation(wrapped):
            child = original(wrapped, **options)
        _owned.register(child)
        return child

    def denied(*args, **kwargs):
        _events.append("parent shell/network denied")
        raise RuntimeError("EA4E73 parent shell/network denied")

    def retain_temporary_tree(path, *args, **kwargs):
        if not Path(path).resolve().is_relative_to(base):
            _events.append("cleanup outside matrix root denied")
            raise RuntimeError("matrix cleanup outside root denied")
        # Preserve disposable fixture evidence rather than deleting files.

    for owner, name, replacement in ((filesystem, "validate_path", validate_owned_pipe),
                                     (subprocess, "Popen", guarded), (os, "system", denied),
                                     (socket.socket, "connect", denied), (socket.socket, "connect_ex", denied),
                                     (shutil, "rmtree", retain_temporary_tree)):
        _originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    global _node
    _node = item.nodeid
    try:
        yield
    finally:
        _node = None


def pytest_sessionfinish(session, exitstatus):
    try:
        _owned.cleanup()
    except Exception as exc:
        _events.append("cleanup: " + str(exc))
    if (_events or set(_admitted) != set(admission.FLAGS)
            or _missing != {MISSING: 1, SYNC: 1} or _pipe_opens != sum(_admitted.values())):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E73_PROCESS_ATTEMPTS={sum(_admitted.values())}")
    terminalreporter.write_line(f"EA4E73_MISSING_EXECUTABLE_NONLAUNCHES={sum(_missing.values())}")
    terminalreporter.write_line(f"EA4E73_PROHIBITED_EVENTS={len(_events)}")
    terminalreporter.write_line(f"EA4E73_QUALIFIED_PIPE_OPENS={_pipe_opens}")
    terminalreporter.write_line(f"EA4E73_OWNED_CHILDREN_ALIVE={sum(child.poll() is None for child in _owned.children)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
