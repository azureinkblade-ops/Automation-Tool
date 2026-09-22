"""Fake-only tests for the separately bounded Kilo 7.7.2 metadata probe."""

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from tools import qualify_ea4e92t_kilo772_metadata as probe


@pytest.fixture
def configured(monkeypatch, tmp_path):
    binary = tmp_path / "kilo.exe"
    binary.write_bytes(b"fake Kilo 7.7.2 metadata executable")
    monkeypatch.setattr(probe, "BINARY", binary)
    monkeypatch.setattr(
        probe, "EXPECTED_HASH", hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        output = (
            "7.7.2\n"
            if argv[1:] == ["--version"]
            else "--format json --pure --agent --model"
        )
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(probe.subprocess, "run", run)
    return calls


def test_only_metadata_arguments_and_isolated_environment(configured):
    result = probe.qualify()
    assert [argv[1:] for argv, _ in configured] == [
        ["--version"],
        ["run", "--help"],
    ]
    assert result["binary_version"] == "7.7.2"
    for _, values in configured:
        assert values["timeout"] == 15
        assert values["shell"] is False
        assert values["stdin"] is subprocess.DEVNULL
        assert values["cwd"] == values["env"]["HOME"]
        assert set(values["env"]) == {
            "SYSTEMROOT",
            "SYSTEMDRIVE",
            "HOME",
            "USERPROFILE",
            "TEMP",
            "TMP",
            "PATH",
            "KILO_CONFIG_DIR",
            "OPENCODE_CONFIG_DIR",
            "OPENCODE_TEST_HOME",
            "OPENCODE_DISABLE_PROJECT_CONFIG",
            "KILO_PURE",
            "OPENCODE_PURE",
            "NO_COLOR",
        }
        assert not any(
            "KEY" in name or "TOKEN" in name or "PASSWORD" in name
            for name in values["env"]
        )


def test_hash_mismatch_prevents_process_start(configured, monkeypatch):
    monkeypatch.setattr(probe, "EXPECTED_HASH", "wrong")
    with pytest.raises(RuntimeError, match="identity changed"):
        probe.qualify()
    assert configured == []


@pytest.mark.parametrize(
    "output,code,error",
    [
        ("wrong", 0, "version mismatch"),
        ("7.7.2", 1, "probe failed"),
    ],
)
def test_failed_version_probe_denies_promotion(
    configured, monkeypatch, output, code, error
):
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=code, stdout=output, stderr=""
        ),
    )
    with pytest.raises(RuntimeError, match=error):
        probe.qualify()


def test_missing_help_flag_denies_promotion(configured, monkeypatch):
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="7.7.2", stderr=""
        ),
    )
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


def test_binary_drift_after_probe_denies_promotion(configured, monkeypatch):
    hashes = iter((probe.EXPECTED_HASH, "changed"))
    monkeypatch.setattr(probe, "_sha256", lambda path: next(hashes))
    with pytest.raises(RuntimeError, match="changed during probe"):
        probe.qualify()
