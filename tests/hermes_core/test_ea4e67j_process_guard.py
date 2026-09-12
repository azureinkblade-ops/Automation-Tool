from types import SimpleNamespace
import subprocess
import sys

import pytest

from tools import ea4e67j_durability_process_guard as guard


@pytest.mark.parametrize("case, message", [
    ("executable", "unqualified executable"),
    ("mode", "unexpected helper mode"),
    ("outside", "outside isolated roots"),
    ("shell", "unexpected launch options"),
    ("capture", "unexpected launch options"),
    ("budget", "exhausted process budget"),
    ("helper_tamper", "qualification identity changed"),
    ("python_tamper", "qualification identity changed"),
    ("network", "network prohibited"),
])
def test_unqualified_launch_is_denied_before_process_creation(tmp_path, monkeypatch, case, message):
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    guard._children.clear()
    guard._denials.clear()
    helper = tmp_path / "helper.py"
    helper.write_bytes(guard.HELPER.read_bytes())
    monkeypatch.setattr(guard, "HELPER", helper)
    config = SimpleNamespace(args=list(guard.NODES), option=SimpleNamespace(basetemp=str(tmp_path / "isolated")))
    guard.pytest_configure(config)
    argv = [sys.executable, str(guard.HELPER), "precommit-crash", str(tmp_path / "isolated-helpers" / "test.sqlite3")]
    options = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if case == "executable":
        argv[0] = str(tmp_path / "unqualified.exe")
    elif case == "mode":
        argv[2] = "execute"
    elif case == "outside":
        argv[3] = str(tmp_path / "live.sqlite3")
    elif case == "shell":
        options["shell"] = True
    elif case == "capture":
        options["stdout"] = None
    elif case == "budget":
        guard._children.extend([object()] * guard.PROCESS_BUDGET)
    elif case == "helper_tamper":
        helper.write_bytes(b"tampered")
    elif case == "python_tamper":
        monkeypatch.setattr(guard, "PYTHON_SHA256", "0" * 64)
    initial_count = len(guard._children)
    try:
        with pytest.raises(RuntimeError, match=message):
            if case == "network":
                import socket
                with socket.socket() as connection:
                    connection.connect(("127.0.0.1", 1))
            else:
                subprocess.Popen(argv, **options)
        assert len(guard._children) == initial_count
        assert len(guard._denials) == 1
    finally:
        guard.pytest_unconfigure(config)
        guard._denials.clear()
        guard._children.clear()


@pytest.mark.parametrize("case", ["selection", "helper", "interpreter", "basetemp"])
def test_startup_rejects_unfrozen_configuration(tmp_path, monkeypatch, case):
    config = SimpleNamespace(args=list(guard.NODES), option=SimpleNamespace(basetemp=None))
    if case == "selection":
        config.args = ["tests/hermes_core/"]
    elif case == "helper":
        monkeypatch.setattr(guard, "HELPER_SHA256", "0" * 64)
    elif case == "interpreter":
        monkeypatch.setattr(guard, "PYTHON_SHA256", "0" * 64)
    with pytest.raises(pytest.UsageError):
        guard.pytest_configure(config)
    assert not guard._originals


def test_unfinished_child_is_killed_reaped_and_fails_session():
    calls = []
    child = SimpleNamespace(poll=lambda: None,
                            kill=lambda: calls.append("kill"),
                            communicate=lambda timeout: calls.append(("reap", timeout)))
    guard._children.append(child)
    session = SimpleNamespace(exitstatus=0)
    try:
        guard.pytest_sessionfinish(session, 0)
        assert calls == ["kill", ("reap", 5)]
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    finally:
        guard._children.clear()
        guard._denials.clear()
