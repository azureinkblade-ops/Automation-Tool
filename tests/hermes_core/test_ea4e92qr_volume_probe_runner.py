"""Fake-process qualification for the unwired volume probe supervisor."""

from datetime import datetime, timedelta, timezone
import hashlib
import io
import subprocess

import pytest

from tools.hermes_core import ea4e92qr_volume_probe_runner as runner_module
from tools.hermes_core.delegated_task import DelegationIntegrityError
from tools.hermes_core.ea4e92qr_volume_probe_runner import (
    BoundedVolumeProbeRunner,
)


SID = "S-1-5-21-1542204473-82821690-3590615374-1001"
CEREMONY = "11111111-1111-1111-1111-111111111111"


class FakeProcess:
    def __init__(self, stdout=b"OBSERVED:PERSISTENT_ACLS_FLAG_ONLY\n",
                 stderr=b"", *, timeout=False):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = None
        self.timeout = timeout
        self.killed = False
        self.wait_count = 0

    def wait(self, timeout):
        self.wait_count += 1
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("fake volume probe", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def fixture(tmp_path, *, process=None, digest=None, deadline=None,
            operator_sid=SID, monotonic=None):
    executable = tmp_path / "inert.exe"
    executable.write_bytes(b"inert fake binary")
    calls = []
    process = process or FakeProcess()

    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    deadline = deadline or (datetime.now(timezone.utc) + timedelta(seconds=60))
    runner = BoundedVolumeProbeRunner(
        str(executable), digest or hashlib.sha256(executable.read_bytes()).hexdigest(),
        r"C:\ProgramData", operator_sid, CEREMONY,
        deadline.strftime("%Y-%m-%dT%H:%M:%SZ"), popen_factory=spawn,
        **({"monotonic": monotonic} if monotonic is not None else {}),
    )
    return executable, runner, calls, process


def test_exact_argv_and_bounded_fake_process(tmp_path):
    executable, runner, calls, _ = fixture(tmp_path)
    outcome = runner()
    assert (outcome.exit_code, outcome.stdout, outcome.stderr) == (
        0, b"OBSERVED:PERSISTENT_ACLS_FLAG_ONLY\n", b"",
    )
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [str(executable), "--native-volume", r"C:\ProgramData",
                    SID, CEREMONY, runner.deadline_utc]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["cwd"] == str(executable.parent)
    assert kwargs["env"]["PATH"] == str(executable.parent)
    assert "DOCKER_HOST" not in kwargs["env"]
    with pytest.raises(DelegationIntegrityError, match="attempt consumed"):
        runner()


@pytest.mark.parametrize("kind", ["digest", "sid", "expired", "too_far", "symlink"])
def test_denial_consumes_attempt_before_spawn(tmp_path, monkeypatch, kind):
    kwargs = {}
    if kind == "digest":
        kwargs["digest"] = "0" * 64
    elif kind == "sid":
        kwargs["operator_sid"] = "not-a-sid"
    elif kind == "expired":
        kwargs["deadline"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif kind == "too_far":
        kwargs["deadline"] = datetime.now(timezone.utc) + timedelta(minutes=5)
    executable, runner, calls, _ = fixture(tmp_path, **kwargs)
    if kind == "symlink":
        monkeypatch.setattr(type(executable), "is_symlink",
                            lambda self: self == executable)
    with pytest.raises(DelegationIntegrityError):
        runner()
    assert calls == []
    with pytest.raises(DelegationIntegrityError, match="attempt consumed"):
        runner()


@pytest.mark.parametrize("process,denial", [
    (FakeProcess(timeout=True), "timeout"),
    (FakeProcess(stdout=b"x" * 257), "output uncertain"),
])
def test_timeout_and_output_overflow_kill_fake_process(tmp_path, process, denial):
    _, runner, calls, _ = fixture(tmp_path, process=process)
    with pytest.raises(DelegationIntegrityError, match=denial):
        runner()
    assert len(calls) == 1
    assert process.killed


def test_nonzero_exit_is_data_not_success(tmp_path):
    process = FakeProcess(stdout=b"DENY:VOLUME_FLAG\n")
    process.returncode = 15
    _, runner, _, _ = fixture(tmp_path, process=process)
    outcome = runner()
    assert outcome.exit_code == 15
    assert outcome.stdout == b"DENY:VOLUME_FLAG\n"


def test_hashing_cannot_extend_expired_deadline(tmp_path, monkeypatch):
    _, runner, calls, _ = fixture(tmp_path)
    real_datetime = datetime
    first = real_datetime.now(timezone.utc)
    observations = iter([first, first + timedelta(minutes=3)])

    class FakeDateTime:
        strptime = staticmethod(real_datetime.strptime)

        @staticmethod
        def now(_timezone):
            return next(observations)

    monkeypatch.setattr(runner_module, "datetime", FakeDateTime)
    with pytest.raises(DelegationIntegrityError, match="deadline denied"):
        runner()
    assert calls == []


def test_expiry_after_process_exit_denies_result(tmp_path, monkeypatch):
    _, runner, calls, process = fixture(tmp_path)
    real_datetime = datetime
    first = real_datetime.now(timezone.utc)
    observations = iter([first, first, first, first,
                         first + timedelta(minutes=3)])

    class FakeDateTime:
        strptime = staticmethod(real_datetime.strptime)

        @staticmethod
        def now(_timezone):
            return next(observations)

    monkeypatch.setattr(runner_module, "datetime", FakeDateTime)
    with pytest.raises(DelegationIntegrityError, match="deadline denied"):
        runner()
    assert len(calls) == 1
    assert process.wait_count >= 1
    assert process.stdout.closed and process.stderr.closed


def test_reader_start_failure_cleans_up_child(tmp_path, monkeypatch):
    _, runner, calls, process = fixture(tmp_path)

    class BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("fake start failure")

        def is_alive(self):
            return False

    monkeypatch.setattr(runner_module.threading, "Thread", BrokenThread)
    with pytest.raises(RuntimeError, match="fake start failure"):
        runner()
    assert len(calls) == 1
    assert process.killed and process.wait_count == 1
    assert process.stdout.closed and process.stderr.closed


def test_reader_start_after_launch_failure_tracks_reader(tmp_path, monkeypatch):
    _, runner, calls, process = fixture(tmp_path)
    real_thread = runner_module.threading.Thread
    launched = []

    class LaunchThenRaise(real_thread):
        def start(self):
            super().start()
            launched.append(self)
            raise RuntimeError("fake post-launch failure")

    monkeypatch.setattr(runner_module.threading, "Thread", LaunchThenRaise)
    with pytest.raises(RuntimeError, match="fake post-launch failure"):
        runner()
    assert len(calls) == 1
    assert len(launched) == 1 and not launched[0].is_alive()
    assert process.killed and process.wait_count == 1
    assert process.stdout.closed and process.stderr.closed


def test_kill_failure_still_waits_and_denies_cleanup(tmp_path):
    class BrokenKillProcess(FakeProcess):
        def kill(self):
            raise OSError("fake kill failure")

    process = BrokenKillProcess(timeout=True)
    _, runner, calls, _ = fixture(tmp_path, process=process)
    with pytest.raises(DelegationIntegrityError, match="cleanup uncertain"):
        runner()
    assert len(calls) == 1
    assert process.wait_count == 2
    assert process.stdout.closed and process.stderr.closed


def test_hashing_elapsed_budget_denies_before_spawn(tmp_path):
    ticks = iter([0.0, 5.1])
    _, runner, calls, _ = fixture(tmp_path, monotonic=lambda: next(ticks))
    with pytest.raises(DelegationIntegrityError, match="deadline denied"):
        runner()
    assert calls == []


def test_monotonic_expiry_denies_result_despite_wall_clock(tmp_path):
    ticks = iter([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.1])
    _, runner, calls, process = fixture(tmp_path,
                                         monotonic=lambda: next(ticks))
    with pytest.raises(DelegationIntegrityError, match="deadline denied"):
        runner()
    assert len(calls) == 1
    assert process.stdout.closed and process.stderr.closed
