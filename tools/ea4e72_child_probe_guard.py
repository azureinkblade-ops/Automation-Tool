"""One-process child-policy qualification authority, test-owned only."""

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from tools import ea4e67m_filesystem_guard as filesystem
from tools import ea4e67y_worker_admission as admission
from tools.ea4e67z_worker_containment import OwnedChildren
from tools.ea4e69_worker_launcher import verify_bootstrap_sources
from tools.ea4e71_owned_pipe_scope import OwnedPipeScope


NODE = "tests/hermes_core/test_ea4e72_child_policy_probe.py::test_installed_child_policy_denies_escape"
HELPER = admission.ROOT / "tools/ea4e72_child_policy_probe.py"
SOURCE_HASHES = {
    HELPER: "3a95c300c547161484eb1363a4b40503279fda7a055a84d5ef1198440a26563f",
    admission.ROOT / "tools/ea4e71_owned_pipe_scope.py": "0b00b4041498d5a39e99e685341ba2359807ba3f3383839f5f31e0ffb357b3ca",
}
_node = None
_attempts = 0
_pipe_opens = 0
_events = []
_originals = []
_owned = OwnedChildren()


def verify_sources():
    verify_bootstrap_sources()
    for path, expected in SOURCE_HASHES.items():
        if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected:
            raise ValueError("probe source mismatch")
    for path, expected in ((admission.PYTHON, admission.PYTHON_SHA256),
                           (Path(subprocess.__file__), "85d29b2bf0249f5436838298c9a60ee93508b1102e9ac43b001f8a7e7ae8f375")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("probe runtime mismatch")


def validate_call(command, options, base, node, attempts):
    if node != NODE or attempts != 0 or not isinstance(command, list) or len(command) != 4:
        raise ValueError("probe node/budget/argv denied")
    if command[:3] != [str(admission.PYTHON), "-B", str(HELPER)]:
        raise ValueError("probe command denied")
    root = Path(command[3]).resolve()
    if not root.is_dir() or root == base or not root.is_relative_to(base):
        raise ValueError("probe child root denied")
    required = {"cwd", "env", "shell", "stdin", "stdout", "stderr", "text", "encoding", "errors"}
    if set(options) != required or Path(options["cwd"]).resolve() != admission.ROOT:
        raise ValueError("probe options denied")
    if options["shell"] is not False or options["text"] is not True or options["encoding"] != "utf-8" or options["errors"] != "replace":
        raise ValueError("probe text/shell denied")
    if any(options[name] != subprocess.PIPE for name in ("stdin", "stdout", "stderr")):
        raise ValueError("probe pipes denied")
    environment = options["env"]
    if set(environment) - {"SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"}:
        raise ValueError("probe environment denied")
    if any(environment.get(name) != os.environ.get(name) for name in ("SYSTEMROOT", "SYSTEMDRIVE")):
        raise ValueError("probe system environment denied")
    if any(environment.get(name) != str(root) for name in ("TEMP", "TMP")):
        raise ValueError("probe temporary environment denied")
    verify_sources()


def pytest_addoption(parser):
    parser.addoption("--ea4e72-one-child-probe", action="store_true", default=False)


def pytest_configure(config):
    if not config.getoption("--ea4e72-one-child-probe") or not config.option.basetemp:
        raise pytest.UsageError("explicit one-child probe envelope required")
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
        global _attempts
        try:
            if args:
                raise ValueError("positional probe options denied")
            validate_call(command, options, base, _node, _attempts)
        except Exception as exc:
            _events.append(str(exc))
            raise RuntimeError("EA4E72 process denied: " + str(exc)) from exc
        _attempts += 1
        with scope.creation(command):
            child = original(command, **options)
        _owned.register(child)
        return child

    def denied(*args, **kwargs):
        _events.append("parent shell/network denied")
        raise RuntimeError("EA4E72 parent shell/network denied")

    for owner, name, replacement in ((filesystem, "validate_path", validate_owned_pipe),
                                     (subprocess, "Popen", guarded), (os, "system", denied),
                                     (socket.socket, "connect", denied), (socket.socket, "connect_ex", denied)):
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
    if _events or _attempts != 1 or _pipe_opens != 1:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E72_PROCESS_ATTEMPTS={_attempts}")
    terminalreporter.write_line(f"EA4E72_PROHIBITED_EVENTS={len(_events)}")
    terminalreporter.write_line(f"EA4E72_QUALIFIED_STDIN_PIPE_OPENS={_pipe_opens}")
    terminalreporter.write_line(f"EA4E72_OWNED_CHILDREN_ALIVE={sum(child.poll() is None for child in _owned.children)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
