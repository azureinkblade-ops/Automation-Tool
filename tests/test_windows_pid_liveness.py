"""CPU-only tests for Windows-safe pid liveness (no os.kill(pid, 0) on nt)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tools import i2v_production_adapter as a

IS_NT = os.name == "nt"


def _exited_child_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_current_pid_alive():
    assert a._pid_alive(os.getpid()) is True
    assert a.default_process_alive(f"pid:{os.getpid()}") is True


def test_exited_child_pid_dead():
    pid = _exited_child_pid()
    assert a._pid_alive(pid) is False
    assert a.default_process_alive(f"pid:{pid}") is False


def test_default_process_alive_unparseable_or_nonpositive_unchanged():
    assert a.default_process_alive("") is True
    assert a.default_process_alive("host-abc") is True
    assert a.default_process_alive("pid:0") is True
    assert a.default_process_alive("pid:-5") is True


@pytest.mark.skipif(not IS_NT, reason="Windows kernel32 path")
def test_windows_path_never_calls_os_kill(monkeypatch):
    calls = []

    def _no_kill(pid, sig):
        calls.append((pid, sig))
        raise AssertionError("os.kill must not be called on nt")

    monkeypatch.setattr(os, "kill", _no_kill)
    assert a._pid_alive(os.getpid()) is True
    assert a._pid_alive(_exited_child_pid()) is False
    assert a.default_process_alive(f"pid:{os.getpid()}") is True
    assert calls == []


@pytest.mark.skipif(not IS_NT, reason="Windows kernel32 path")
def test_windows_bogus_pid_dead():
    # Large pid not in use -> OpenProcess ERROR_INVALID_PARAMETER -> dead
    assert a._pid_alive(0x7FFFFFF0) is False


def test_nt_dispatch_uses_windows_helper_not_os_kill(monkeypatch):
    seen = []
    monkeypatch.setattr(a.os, "name", "nt")
    monkeypatch.setattr(a, "_pid_alive_windows", lambda pid: seen.append(pid) or True)
    monkeypatch.setattr(a.os, "kill", lambda pid, sig: (_ for _ in ()).throw(AssertionError(f"os.kill({pid},{sig})")))
    assert a._pid_alive(1234) is True
    assert seen == [1234]


@pytest.mark.parametrize(
    "exc,expected",
    [(None, True), (ProcessLookupError(), False), (PermissionError(), True), (OSError(), True)],
)
def test_posix_semantics_preserved(monkeypatch, exc, expected):
    calls = []

    def _kill(pid, sig):
        calls.append((pid, sig))
        if exc is not None:
            raise exc

    monkeypatch.setattr(a.os, "name", "posix")
    monkeypatch.setattr(a.os, "kill", _kill)
    assert a._pid_alive(4321) is expected
    assert calls == [(4321, 0)]
