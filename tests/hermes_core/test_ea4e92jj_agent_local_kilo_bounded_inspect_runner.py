"""Fake process tests only; no Docker daemon is contacted."""

import hashlib
import io
import subprocess

import pytest

from tools.hermes_core.agent_local_kilo_bounded_inspect_runner import (
    BoundedDockerInspectRunner,
)
from tools.hermes_core.delegated_task import DelegationIntegrityError


HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
ID = "a" * 64
INDEX = "sha256:" + "b" * 64


class FakeProcess:
    def __init__(self, stdout=b'[{"Id":"ok"}]', stderr=b"", *, timeout=False):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = 0
        self.timeout = timeout
        self.killed = False

    def wait(self, timeout):
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("fake docker", timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def fixture(tmp_path, process=None):
    executable = tmp_path / "docker.exe"
    executable.write_bytes(b"inert fake executable")
    config = tmp_path / "empty-config"
    config.mkdir()
    calls = []
    process = process or FakeProcess()

    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    runner = BoundedDockerInspectRunner(
        str(executable), hashlib.sha256(executable.read_bytes()).hexdigest(),
        str(config), popen_factory=spawn,
    )
    return executable, config, runner, calls, process


def test_exact_read_only_argv_and_sanitized_process(tmp_path):
    executable, config, runner, calls, _ = fixture(tmp_path)
    argv = (str(executable), "--host", HOST, "image", "inspect",
            "--platform", "linux/amd64", INDEX)
    assert runner(argv, timeout_seconds=5, max_output_bytes=1024 * 1024) == b'[{"Id":"ok"}]'
    assert len(calls) == 1
    assert calls[0][0] == list(argv)
    kwargs = calls[0][1]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.PIPE
    assert kwargs["cwd"] == str(config)
    assert kwargs["env"]["DOCKER_CONFIG"] == str(config)
    assert kwargs["env"]["PATH"] == str(executable.parent)
    assert "DOCKER_HOST" not in kwargs["env"]


@pytest.mark.parametrize("tail", [
    ("container", "start", ID),
    ("container", "inspect", "bad"),
    ("image", "inspect", INDEX),
    ("network", "inspect", INDEX),
    ("container", "inspect", ID, "extra"),
])
def test_other_commands_denied_before_spawn(tmp_path, tail):
    executable, _, runner, calls, _ = fixture(tmp_path)
    with pytest.raises(DelegationIntegrityError, match="command denied"):
        runner((str(executable), "--host", HOST, *tail),
               timeout_seconds=5, max_output_bytes=1024 * 1024)
    assert calls == []


def test_changed_executable_and_nonempty_config_denied(tmp_path):
    executable, config, runner, calls, _ = fixture(tmp_path)
    argv = (str(executable), "--host", HOST, "container", "inspect", ID)
    executable.write_bytes(b"changed")
    with pytest.raises(DelegationIntegrityError, match="executable changed"):
        runner(argv, timeout_seconds=5, max_output_bytes=1024 * 1024)
    executable.write_bytes(b"inert fake executable")
    (config / "config.json").write_text("{}", encoding="ascii")
    with pytest.raises(DelegationIntegrityError, match="config denied"):
        runner(argv, timeout_seconds=5, max_output_bytes=1024 * 1024)
    assert calls == []


@pytest.mark.parametrize("process", [
    FakeProcess(stdout=b"x" * (1024 * 1024 + 1)),
    FakeProcess(stderr=b"error"),
    FakeProcess(timeout=True),
])
def test_overflow_stderr_and_timeout_fail_closed(tmp_path, process):
    executable, _, runner, _, _ = fixture(tmp_path, process)
    argv = (str(executable), "--host", HOST, "network", "inspect", ID)
    expected_kill = process.timeout or len(process.stdout.getvalue()) > 1024 * 1024
    with pytest.raises(DelegationIntegrityError, match="execution denied"):
        runner(argv, timeout_seconds=5, max_output_bytes=1024 * 1024)
    if expected_kill:
        assert process.killed
