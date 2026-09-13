"""Explicit two-probe qualification envelope; never a receiver exception."""

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from tools import ea4e67y_worker_admission as admission
from tools.ea4e67z_worker_containment import OwnedChildren
from tools.ea4e69_worker_launcher import verify_bootstrap_sources
from tools.ea4e71_owned_pipe_scope import OwnedPipeScope
from tools import ea4e67m_filesystem_guard as filesystem


PREFIX = "tests/hermes_core/test_ea4e70_worker_process_qualification.py::"
ALLOWED = {
    PREFIX + "test_guarded_worker_accepts": admission.WORKER + "RealSpawnTests::test_valid_probe_returns_started",
    PREFIX + "test_timeout_reaps_owned_child": admission.WORKER + "TimeoutMechanicsTests::test_ack_timeout_terminates_only_owned_child",
}
LAUNCHER_HASH = "126caefa8466bfd806c0c6d1268791ab3eeea6a2c42ef58ccf53764fee009887"
_node = None
_counts = {}
_admitted = {}
_events = []
_originals = []
_owned = OwnedChildren()
_pipe_opens = 0


def pytest_addoption(parser):
    parser.addoption("--ea4e70-two-worker-probes", action="store_true", default=False)


def pytest_configure(config):
    if not config.getoption("--ea4e70-two-worker-probes") or not config.option.basetemp:
        raise pytest.UsageError("explicit two-worker-probe envelope and fresh basetemp required")
    base = Path(config.option.basetemp).resolve()
    verify_bootstrap_sources()
    content = (admission.ROOT / "tools/ea4e69_worker_launcher.py").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != LAUNCHER_HASH:
        raise pytest.UsageError("launcher source identity mismatch")
    original = subprocess.Popen
    scope_source = (admission.ROOT / "tools/ea4e71_owned_pipe_scope.py").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(scope_source).hexdigest() != "0b00b4041498d5a39e99e685341ba2359807ba3f3383839f5f31e0ffb357b3ca":
        raise pytest.UsageError("owned-pipe source mismatch")
    if hashlib.sha256(Path(subprocess.__file__).read_bytes()).hexdigest() != "85d29b2bf0249f5436838298c9a60ee93508b1102e9ac43b001f8a7e7ae8f375":
        raise pytest.UsageError("subprocess constructor source mismatch")
    pipe_scope = OwnedPipeScope(original.__init__.__code__)
    original_validate = filesystem.validate_path

    def validate_owned_pipe(value, root):
        global _pipe_opens
        audit_frame = sys._getframe(1)
        if (type(value) is int and audit_frame.f_code is filesystem.audit.__code__
                and pipe_scope.allows(audit_frame.f_locals.get("event"),
                                      audit_frame.f_locals.get("args", ()), audit_frame.f_back)):
            _pipe_opens += 1
            return
        return original_validate(value, root)

    _originals.append((filesystem, "validate_path", original_validate))
    filesystem.validate_path = validate_owned_pipe

    def guarded(command, *args, **kwargs):
        try:
            if _node not in ALLOWED or _counts.get(_node, 0) >= 1 or sum(_counts.values()) >= 2:
                raise ValueError("unqualified test node or exhausted process budget")
            if args or not isinstance(command, list) or len(command) < 8:
                raise ValueError("unqualified process call")
            if command[:5] != [str(admission.PYTHON), "-B", str(admission.ROOT / "tools/ea4e68_worker_entrypoint.py"), ALLOWED[_node], str(base)]:
                raise ValueError("unqualified guarded entrypoint argv")
            required = {"cwd", "env", "shell", "stdin", "stdout", "stderr", "text", "encoding", "errors"}
            if set(kwargs) != required or kwargs["shell"] is not False or kwargs["text"] is not True:
                raise ValueError("unqualified process options")
            if any(kwargs[name] != subprocess.PIPE for name in ("stdin", "stdout", "stderr")):
                raise ValueError("unqualified pipe configuration")
            if kwargs["encoding"] != "utf-8" or kwargs["errors"] != "replace":
                raise ValueError("unqualified text configuration")
            admission.validate_worker_launch(ALLOWED[_node], command[5:], kwargs["cwd"], kwargs["env"], base, _admitted)
            verify_bootstrap_sources()
        except Exception as exc:
            _events.append(str(exc))
            raise RuntimeError("EA4E70 process denied: " + str(exc)) from exc
        _counts[_node] = _counts.get(_node, 0) + 1
        _admitted[ALLOWED[_node]] = _admitted.get(ALLOWED[_node], 0) + 1
        with pipe_scope.creation(command):
            child = original(command, **kwargs)
        _owned.register(child)
        return child

    def denied(*args, **kwargs):
        _events.append("shell/network capability denied")
        raise RuntimeError("EA4E70 shell/network denied")

    for owner, name, replacement in ((subprocess, "Popen", guarded), (os, "system", denied),
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
    if _events or _counts != {node: 1 for node in ALLOWED} or _pipe_opens != 2:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E70_PROCESS_ATTEMPTS={sum(_counts.values())}")
    terminalreporter.write_line(f"EA4E70_PROHIBITED_EVENTS={len(_events)}")
    terminalreporter.write_line(f"EA4E71_QUALIFIED_STDIN_PIPE_OPENS={_pipe_opens}")
    terminalreporter.write_line(f"EA4E70_OWNED_CHILDREN_ALIVE={sum(child.poll() is None for child in _owned.children)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
