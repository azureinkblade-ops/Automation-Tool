"""Synthetic tests for the standalone Buildx version probe; no plugin runs."""

import io
import subprocess

import pytest

from tools import ea4e92vz_buildx_version_probe as probe


class FakeProcess:
    def __init__(self, stdout=b"buildx v0.1", stderr=b"", code=0, timeout=False):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = code
        self.timeout = timeout
        self.killed = False

    def wait(self, timeout):
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("buildx", timeout)
        return self.returncode

    def poll(self):
        return None if self.timeout and not self.killed else self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -1


def test_pinned_version_invocation_isolated_and_redacted(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(probe, "_sha256", lambda path: "a" * 64)
    monkeypatch.setattr(probe.subprocess, "Popen",
                        lambda *a, **k: (seen.append((a, k)), FakeProcess())[1])
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    assert probe.probe_version(binary, "a" * 64) is True
    assert seen[0][0][0][1] == "version"
    assert seen[0][1]["env"] == {
        "SYSTEMROOT": probe.os.environ.get("SYSTEMROOT", r"C:\Windows")}
    assert seen[0][1]["stdin"] == subprocess.DEVNULL
    assert seen[0][1]["shell"] is False


def test_invalid_pin_denied_before_start(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("plugin started"))
    with pytest.raises(probe.ProbeDenied, match="invalid Buildx pin"):
        probe.probe_version(tmp_path / "docker-buildx.exe", "bad")


def test_hash_mismatch_denied_before_start(monkeypatch, tmp_path):
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(probe.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("plugin started"))
    with pytest.raises(probe.ProbeDenied, match="identity mismatch"):
        probe.probe_version(binary, "a" * 64)


def test_launch_error_redacted(monkeypatch, tmp_path):
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(probe, "_sha256", lambda path: "a" * 64)

    def deny(*args, **kwargs):
        raise OSError("private path and credential")

    monkeypatch.setattr(probe.subprocess, "Popen", deny)
    with pytest.raises(probe.ProbeDenied, match="process unavailable") as error:
        probe.probe_version(binary, "a" * 64)
    assert "private path" not in str(error.value)


def test_nonzero_is_fixed_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "_sha256", lambda path: "a" * 64)
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(probe.subprocess, "Popen",
                        lambda *a, **k: FakeProcess(stderr=b"private path", code=1))
    assert probe.probe_version(binary, "a" * 64) is False


def test_oversize_output_denied(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "_sha256", lambda path: "a" * 64)
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(probe.subprocess, "Popen",
                        lambda *a, **k: FakeProcess(stdout=b"x" * 4097))
    with pytest.raises(probe.ProbeDenied, match="output bound"):
        probe.probe_version(binary, "a" * 64)


def test_deadline_kills_exact_process(monkeypatch, tmp_path):
    fake = FakeProcess(timeout=True)
    monkeypatch.setattr(probe, "_sha256", lambda path: "a" * 64)
    binary = tmp_path / "docker-buildx.exe"
    binary.write_bytes(b"synthetic")
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *a, **k: fake)
    with pytest.raises(probe.ProbeDenied, match="deadline exceeded"):
        probe.probe_version(binary, "a" * 64)
    assert fake.killed
