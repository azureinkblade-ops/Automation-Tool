"""Fake-only safety checks for the unexecuted Kilo 7.7.9 metadata probe."""

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from tools import qualify_ea4e92ah_kilo779_metadata as probe


@pytest.fixture
def configured(monkeypatch, tmp_path):
    binary = tmp_path / "kilo.exe"
    binary.write_bytes(b"fake Kilo 7.7.9 metadata executable")
    monkeypatch.setattr(probe, "BINARY", binary)
    monkeypatch.setattr(
        probe, "EXPECTED_HASH", hashlib.sha256(binary.read_bytes()).hexdigest())
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        output = (
            "7.7.9\n" if argv[1:] == ["--version"]
            else "--format json --pure --agent --model"
        )
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(probe.subprocess, "run", run)
    return calls


def test_only_two_metadata_commands_and_isolated_environment(configured):
    result = probe.qualify()
    assert [argv[1:] for argv, _ in configured] == [
        ["--version"], ["run", "--help"]]
    assert result["binary_version"] == "7.7.9"
    assert len(result["probes"]) == 2
    for _, values in configured:
        assert values["timeout"] == 15
        assert values["shell"] is False
        assert values["stdin"] is subprocess.DEVNULL
        assert values["cwd"] == values["env"]["HOME"]
        assert set(values["env"]) == {
            "SYSTEMROOT", "SYSTEMDRIVE", "HOME", "USERPROFILE", "TEMP",
            "TMP", "PATH", "KILO_CONFIG_DIR", "OPENCODE_CONFIG_DIR",
            "OPENCODE_TEST_HOME", "OPENCODE_DISABLE_PROJECT_CONFIG",
            "KILO_PURE", "OPENCODE_PURE", "NO_COLOR",
        }
        assert not any(
            token in name for name in values["env"]
            for token in ("KEY", "TOKEN", "PASSWORD"))


def test_hash_mismatch_prevents_any_launch(configured, monkeypatch):
    monkeypatch.setattr(probe, "EXPECTED_HASH", "wrong")
    with pytest.raises(RuntimeError, match="identity changed"):
        probe.qualify()
    assert configured == []


def test_file_drift_before_second_command_stops_second_launch(configured, monkeypatch):
    hashes = iter((probe.EXPECTED_HASH, probe.EXPECTED_HASH,
                   probe.EXPECTED_HASH, "changed"))
    monkeypatch.setattr(probe, "_sha256", lambda path: next(hashes))
    with pytest.raises(RuntimeError, match="identity changed"):
        probe.qualify()
    assert len(configured) == 1


@pytest.mark.parametrize("version,code,message", [
    ("wrong", 0, "version mismatch"),
    ("7.7.9", 1, "probe failed"),
])
def test_failed_first_probe_stops_before_help(
        configured, monkeypatch, version, code, message):
    attempts = []

    def fail(argv, **kwargs):
        attempts.append(argv)
        return SimpleNamespace(returncode=code, stdout=version, stderr="")

    monkeypatch.setattr(
        probe.subprocess, "run", fail)
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
            return SimpleNamespace(returncode=0, stdout="x" * 65537,
                                   stderr="")
        return original(argv, **kwargs)

    monkeypatch.setattr(probe.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="output exceeds"):
        probe.qualify()
