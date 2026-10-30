"""Synthetic, no-Docker tests for the opt-in Buildx inspection denial path."""

import io
from pathlib import Path

import pytest

from tools import ea4e92rm_container_smoke as smoke


@pytest.mark.parametrize(("stderr", "category"), [
    (b"docker: 'buildx' is not a docker command. private path", "plugin_unavailable"),
    (b"no builder 'default' found: private path", "builder_missing"),
    (b"Cannot connect to the Docker daemon: private path", "daemon_unavailable"),
    (b"Access is denied: private path", "permission_denied"),
    (b"unknown flag: --bootstrap", "cli_incompatible"),
    (b"unexpected private path and credential", "unclassified"),
])
def test_fixed_category_never_includes_stderr(stderr, category):
    result = smoke._fixed_buildx_inspect_category(stderr)
    assert result == category
    assert b"private path" not in result.encode()


def test_inspect_failure_only_classified_when_opted_in(monkeypatch):
    class FailedProcess:
        stdin = io.BytesIO()
        stdout = io.BytesIO()
        stderr = io.BytesIO(b"no builder 'default' found: private path")
        returncode = 1

        def wait(self, timeout):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(smoke, "_hash_file", lambda path: "a" * 64)
    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *a, **k: FailedProcess())
    client = smoke.DockerCli(Path(__file__), "a" * 64,
                             classify_buildx_inspect_failure=True)
    with pytest.raises(smoke.BuildxInspectDenied) as error:
        client.invoke(("buildx", "inspect", "default"), timeout=1,
                      output_limit=65536)
    assert error.value.category == "builder_missing"
    assert "private path" not in str(error.value)

    with pytest.raises(smoke.SmokeDenied, match="Docker CLI command failed"):
        client.invoke(("buildx", "inspect", "other"), timeout=1,
                      output_limit=65536)
    default_client = smoke.DockerCli(Path(__file__), "a" * 64)
    with pytest.raises(smoke.SmokeDenied, match="Docker CLI command failed"):
        default_client.invoke(("buildx", "inspect", "default"), timeout=1,
                              output_limit=65536)


def test_invalid_diagnostic_mode_denied(monkeypatch):
    monkeypatch.setattr(smoke, "_hash_file", lambda path: "a" * 64)
    with pytest.raises(smoke.SmokeDenied, match="invalid builder diagnostic mode"):
        smoke.DockerCli(Path(__file__), "a" * 64,
                        classify_buildx_inspect_failure=1)


def test_pinned_user_config_is_exact_inspect_only(monkeypatch):
    seen = []

    class SuccessProcess:
        stdin = io.BytesIO()
        stdout = io.BytesIO(b"Name: default\nDriver: docker\n")
        stderr = io.BytesIO()
        returncode = 0

        def wait(self, timeout):
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(smoke, "_hash_file", lambda path: "a" * 64)
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: (seen.append(k), SuccessProcess())[1])
    client = smoke.DockerCli(Path(__file__), "a" * 64,
                             classify_buildx_inspect_failure=True,
                             user_config_sha256="a" * 64)
    assert client.invoke(("buildx", "inspect", "default"), timeout=1) == (
        b"Name: default\nDriver: docker\n")
    assert seen[0]["env"] == {
        "SYSTEMROOT": smoke.os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "DOCKER_CONFIG": str(Path.home() / ".docker"),
    }
    with pytest.raises(smoke.SmokeDenied, match="builder config scope mismatch"):
        client.invoke(("container", "ls"), timeout=1)
    assert len(seen) == 1


def test_user_config_drift_denied_before_process(monkeypatch):
    hashes = iter(["a" * 64, "a" * 64, "b" * 64])
    monkeypatch.setattr(smoke, "_hash_file", lambda path: next(hashes))
    monkeypatch.setattr(smoke.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("Docker process started"))
    client = smoke.DockerCli(Path(__file__), "a" * 64,
                             classify_buildx_inspect_failure=True,
                             user_config_sha256="a" * 64)
    with pytest.raises(smoke.SmokeDenied, match="Docker config identity mismatch"):
        client.invoke(("buildx", "inspect", "default"), timeout=1)


def test_user_config_requires_classifier_and_valid_pin(monkeypatch):
    monkeypatch.setattr(smoke, "_hash_file", lambda path: "a" * 64)
    with pytest.raises(smoke.SmokeDenied, match="invalid builder config pin"):
        smoke.DockerCli(Path(__file__), "a" * 64,
                        user_config_sha256="a" * 64)
    with pytest.raises(smoke.SmokeDenied, match="invalid builder config pin"):
        smoke.DockerCli(Path(__file__), "a" * 64,
                        classify_buildx_inspect_failure=True,
                        user_config_sha256="not-a-hash")
    with pytest.raises(smoke.SmokeDenied, match="invalid builder config pin"):
        smoke.DockerCli(Path(__file__), "a" * 64,
                        classify_buildx_inspect_failure=True,
                        user_config_sha256=7)
