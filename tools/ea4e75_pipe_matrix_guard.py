"""Fifteen deterministic pipe tests; no installed receiver or -c authority."""

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import threading

import pytest

from tools import ea4e74_pipe_inventory as inventory
from tools.ea4e67z_worker_containment import OwnedChildren
from tools.ea4e72_child_probe_guard import verify_sources


HELPER = inventory.admission.ROOT / "tools/ea4e74_pipe_probe.py"
HASHES = {
    HELPER: "3f55c41a2515f7a8a40f9c0d605e17b72278a0798b1454121ddd9bd4383880c8",
    inventory.admission.ROOT / "tools/ea4e74_pipe_inventory.py": "f70201f90b0af6b01c70e2c3a692e958c414f516e33eb0f8ff6eb4bfffa1ffeb",
}
_node = None
_counts = {}
_events = []
_originals = []
_owned = OwnedChildren()
_readers = []


def verify_pipe_sources():
    verify_sources()
    for path, expected in HASHES.items():
        if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected:
            raise ValueError("pipe source identity mismatch")


def validate_call(node, command, options, base, counts):
    if counts.get(node, 0) >= 1 or sum(counts.values()) >= len(inventory.CASES):
        raise ValueError("pipe creation budget exhausted")
    required = {"cwd", "env", "shell", "stdin", "stdout", "stderr", "creationflags"}
    if set(options) != required or options["env"] != {} or options["shell"] is not False:
        raise ValueError("pipe options/environment denied")
    if options["stdin"] != subprocess.DEVNULL or any(options[name] != subprocess.PIPE for name in ("stdout", "stderr")):
        raise ValueError("pipe byte stream options denied")
    if options["creationflags"] != (getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0):
        raise ValueError("pipe Windows flags denied")
    case = inventory.pipe_case(node, command, options["cwd"], base)
    verify_pipe_sources()
    return case


def pytest_addoption(parser):
    parser.addoption("--ea4e75-fifteen-pipe-probes", action="store_true", default=False)


def pytest_configure(config):
    if not config.getoption("--ea4e75-fifteen-pipe-probes") or not config.option.basetemp:
        raise pytest.UsageError("explicit fifteen-pipe qualification envelope required")
    verify_pipe_sources()
    base = Path(config.option.basetemp).resolve()
    original = subprocess.Popen

    def guarded(command, *args, **options):
        try:
            if args:
                raise ValueError("positional pipe options denied")
            case = validate_call(_node, command, options, base, _counts)
        except Exception as exc:
            _events.append(str(exc))
            raise RuntimeError("EA4E75 process denied: " + str(exc)) from exc
        _counts[_node] = _counts.get(_node, 0) + 1
        root = Path(options["cwd"]).resolve()
        environment = {name: os.environ[name] for name in ("SYSTEMROOT", "SYSTEMDRIVE") if name in os.environ}
        environment.update(TEMP=str(root), TMP=str(root))
        qualified_options = dict(options, env=environment)
        child = original([command[0], "-B", str(HELPER), case, str(root)], **qualified_options)
        _owned.register(child)
        return child

    def denied(*args, **kwargs):
        _events.append("parent shell/network denied")
        raise RuntimeError("EA4E75 parent shell/network denied")

    for owner, name, replacement in ((subprocess, "Popen", guarded), (os, "system", denied),
                                     (socket.socket, "connect", denied), (socket.socket, "connect_ex", denied)):
        _originals.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)


def pytest_collection_finish(session):
    from tools.hermes_core.opencode_adapter import OpenCodeLiveProcess
    original = OpenCodeLiveProcess.start

    def tracked_start(self, argv, stdin_data):
        pid = original(self, argv, stdin_data)
        owned = self._owned[pid]
        _readers.extend(reader for reader in (owned.stdout_reader, owned.stderr_reader) if reader is not None)
        return pid

    _originals.append((OpenCodeLiveProcess, "start", original))
    OpenCodeLiveProcess.start = tracked_start


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
        for reader in _readers:
            # Invoke class methods because stuck-reader tests replace instance methods.
            threading.Thread.join(reader, timeout=1)
            if threading.Thread.is_alive(reader):
                raise RuntimeError("owned pipe reader remains alive")
    except Exception as exc:
        _events.append("cleanup: " + str(exc))
    if _events or _counts != {node: 1 for node in inventory.CASES}:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"EA4E75_PROCESS_ATTEMPTS={sum(_counts.values())}")
    terminalreporter.write_line(f"EA4E75_PROHIBITED_EVENTS={len(_events)}")
    terminalreporter.write_line(f"EA4E75_OWNED_CHILDREN_ALIVE={sum(child.poll() is None for child in _owned.children)}")
    terminalreporter.write_line(f"EA4E75_OWNED_READERS_ALIVE={sum(threading.Thread.is_alive(reader) for reader in _readers)}")
    for event in _events:
        terminalreporter.write_line(event)


def pytest_unconfigure(config):
    for owner, name, original in reversed(_originals):
        setattr(owner, name, original)
    _originals.clear()
