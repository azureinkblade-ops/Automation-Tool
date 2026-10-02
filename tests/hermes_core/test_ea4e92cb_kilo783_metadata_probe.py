"""Fake-only checks for the unexecuted Kilo 7.8.3 metadata probe."""

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from tools import qualify_ea4e92cb_kilo783_metadata as probe


@pytest.fixture
def configured(monkeypatch, tmp_path):
    binary = tmp_path / "kilo.exe"
    binary.write_bytes(b"fake Kilo 7.8.3 metadata executable")
    monkeypatch.setattr(probe, "BINARY", binary)
    monkeypatch.setattr(probe, "EXPECTED_HASH", hashlib.sha256(binary.read_bytes()).hexdigest())
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        output = "7.8.3\n" if argv[1:] == ["--version"] else "--format json --pure --agent --model"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(probe.subprocess, "run", run)
    return calls


def test_exact_commands_and_isolated_environment(configured):
    result = probe.qualify()
    assert [argv[1:] for argv, _ in configured] == [["--version"], ["run", "--help"]]
    assert result["binary_version"] == "7.8.3"
    assert result["binary_sha256"] == probe.EXPECTED_HASH
    assert len(result["probes"]) == 2
    for _, kwargs in configured:
        assert kwargs["timeout"] == 15
        assert kwargs["shell"] is False
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["cwd"] == kwargs["env"]["HOME"]
        assert set(kwargs["env"]) == {
            "SYSTEMROOT", "SYSTEMDRIVE", "HOME", "USERPROFILE", "TEMP", "TMP",
            "PATH", "KILO_CONFIG_DIR", "OPENCODE_CONFIG_DIR", "OPENCODE_TEST_HOME",
            "OPENCODE_DISABLE_PROJECT_CONFIG", "KILO_PURE", "OPENCODE_PURE", "NO_COLOR",
        }
        assert not any(token in name for name in kwargs["env"] for token in ("KEY", "TOKEN", "PASSWORD"))


def test_identity_mismatch_prevents_launch(configured, monkeypatch):
    monkeypatch.setattr(probe, "EXPECTED_HASH", "wrong")
    with pytest.raises(RuntimeError, match="identity changed"):
        probe.qualify()
    assert configured == []


def test_drift_prevents_second_launch(configured, monkeypatch):
    hashes = iter((probe.EXPECTED_HASH, probe.EXPECTED_HASH, probe.EXPECTED_HASH, "changed"))
    monkeypatch.setattr(probe, "_sha256", lambda path: next(hashes))
    with pytest.raises(RuntimeError, match="identity changed"):
        probe.qualify()
    assert len(configured) == 1


@pytest.mark.parametrize("version,code,message", [
    ("wrong", 0, "version mismatch"),
    ("7.8.3", 1, "probe failed"),
])
def test_first_probe_failure_stops_before_help(configured, monkeypatch, version, code, message):
    attempts = []

    def fail(argv, **kwargs):
        attempts.append(argv)
        return SimpleNamespace(returncode=code, stdout=version, stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match=message):
        probe.qualify()
    assert len(attempts) == 1


def test_missing_help_option_denies(configured, monkeypatch):
    original = probe.subprocess.run

    def run(argv, **kwargs):
        if argv[1:] == ["run", "--help"]:
            return SimpleNamespace(returncode=0, stdout="--format json", stderr="")
        return original(argv, **kwargs)

    monkeypatch.setattr(probe.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="option missing"):
        probe.qualify()


def test_timeout_is_not_retried(configured, monkeypatch):
    attempts = []

    def timeout(argv, **kwargs):
        attempts.append(argv)
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(probe.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        probe.qualify()
    assert len(attempts) == 1


def test_oversize_output_denies(configured, monkeypatch):
    original = probe.subprocess.run

    def run(argv, **kwargs):
        if argv[1:] == ["run", "--help"]:
            return SimpleNamespace(returncode=0, stdout="x" * 65537, stderr="")
        return original(argv, **kwargs)

    monkeypatch.setattr(probe.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="output exceeds"):
        probe.qualify()
